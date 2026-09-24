"""
Intent and entity extraction.

Deterministic pattern matching, tried most-specific first. This runs before
any model call, so the common cases ("I slept 6 hours") are free, instant
and identical every time - which matters for a live demo.

parse() returns {intent, entities, confidence}. A confidence below
MIN_CONFIDENCE means the caller should fall back to the language model.
"""
import re

MIN_CONFIDENCE = 0.5

# Words that mean the number is NOT a measurement to log.
_NEGATORS = ("how many", "how much", "what is my", "what's my", "show me",
             "do i need", "should i")

# Written numbers we accept in place of digits.
_WORD_NUMBERS = {
    "half": 0.5, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "a couple of": 2, "a couple": 2, "a few": 3,
}

NUM = r"(\d+(?:\.\d+)?)"

# (intent, compiled pattern, entity names in group order)
# Order matters: the first match wins, so put specific patterns above general.
PATTERNS: list[tuple[str, re.Pattern, tuple]] = [
    # --- blood pressure: two numbers, must beat the single-number rules ---
    ("log_vital_bp", re.compile(
        rf"(?:blood pressure|bp)\D{{0,12}}{NUM}\s*(?:/|over|by)\s*{NUM}"),
     ("systolic", "diastolic")),

    # --- vitals ---
    ("log_vital_hr", re.compile(
        rf"(?:heart rate|pulse|resting hr|bpm)\D{{0,12}}{NUM}|{NUM}\s*bpm"),
     ("heart_rate",)),
    ("log_vital_weight", re.compile(
        rf"(?:weigh|weight)\D{{0,12}}{NUM}\s*(?:kg|kilo|kilos|kilograms)?"),
     ("weight_kg",)),
    ("log_vital_height", re.compile(
        rf"(?:height|tall)\D{{0,12}}{NUM}\s*(?:cm|centimet)?"),
     ("height_cm",)),

    # --- mood: "mood is 6", "feeling 4 out of 10" ---
    ("log_mood", re.compile(
        rf"(?:mood|feeling|felt)\D{{0,12}}{NUM}\s*(?:out of 10|/\s*10)?"),
     ("mood_score",)),
    ("log_mood", re.compile(rf"{NUM}\s*(?:out of 10|/\s*10)"), ("mood_score",)),

    # --- sleep ---
    ("log_sleep", re.compile(
        rf"(?:slept|sleep|sleeping)\D{{0,12}}{NUM}\s*(?:h|hr|hrs|hour|hours)?"),
     ("sleep_hours",)),
    ("log_sleep", re.compile(
        rf"{NUM}\s*(?:h|hr|hrs|hours?)\s*(?:of\s*)?(?:sleep|rest)"),
     ("sleep_hours",)),

    # --- activity ---
    ("log_steps", re.compile(rf"{NUM}\s*steps|steps\D{{0,12}}{NUM}"),
     ("steps",)),
    ("log_exercise", re.compile(
        rf"\b(?:exercis\w*|workout|worked out|ran|run|jog\w*|walk\w*|gym|"
        rf"cycl\w*|swim\w*|yoga)\b\D{{0,14}}{NUM}\s*(?:min|mins|minutes)?"),
     ("exercise_mins",)),
    ("log_exercise", re.compile(
        rf"{NUM}\s*(?:min|mins|minutes)\s*(?:of\s*)?"
        rf"(?:exercise|workout|walk\w*|run\w*|yoga|gym|cycling|swimming)"),
     ("exercise_mins",)),

    # --- water: litres converted to glasses (1 glass ~ 250ml) ---
    ("log_water_litres", re.compile(
        rf"{NUM}\s*(?:l|litre|litres|liter|liters)\b"), ("litres",)),
    ("log_water", re.compile(
        rf"(?:drank|drink|had|log)\D{{0,12}}{NUM}\s*"
        rf"(?:glass|glasses|cup|cups|bottle|bottles)"), ("water_glasses",)),
    ("log_water", re.compile(
        rf"{NUM}\s*(?:glass|glasses|cup|cups)\s*(?:of\s*water)?"),
     ("water_glasses",)),
    ("log_water", re.compile(rf"water\D{{0,12}}{NUM}"), ("water_glasses",)),

    # --- food: calories last, it is the most generic number ---
    ("log_meal", re.compile(rf"{NUM}\s*(?:kcal|calories|cals|cal)\b"),
     ("calories",)),
    ("log_meal", re.compile(
        rf"(?:ate|eat|had|breakfast|lunch|dinner|snack)\D{{0,20}}{NUM}"),
     ("calories",)),
]

# Intents that need no number at all.
KEYWORD_INTENTS: list[tuple[str, tuple]] = [
    ("report", ("doctor summary", "summary for my doctor", "health summary",
                "generate report", "make a report", "for my doctor",
                "print report", "export my data")),
    ("assessment", ("assess", "assessment", "full review", "whole picture",
                    "maintenance calories", "how many calories should i",
                    "am i eating enough", "am i overeating", "am i under",
                    "tdee", "energy needs", "check my diet", "review me",
                    "what is wrong with me", "whats wrong with me")),
    ("progress", ("my streak", "streak", "my progress", "achievements",
                  "badges", "rings", "my level", "how many points",
                  "goals today", "my goals")),
    ("insights", ("insights", "patterns", "what's going on", "whats going on",
                  "connect", "correlate", "analyse", "analyze", "trends",
                  "anything unusual")),
    ("checkin", ("how am i", "check in", "checkin", "summary", "status",
                 "overview", "how am i doing", "daily report")),
    ("log_medication_taken", ("took my", "taken my", "took it", "had my pill",
                              "took my medicine", "took my medication")),
    ("add_medication", ("i take ", "add medication", "remind me to take",
                        "i'm on ", "im on ", "prescribed")),
    ("help", ("what can you do", "help", "commands", "how do i use")),
]


def _to_number(raw: str) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _expand_word_numbers(text: str) -> str:
    """Turn 'I drank two glasses' into 'I drank 2 glasses'."""
    out = text
    for word, value in sorted(_WORD_NUMBERS.items(), key=lambda kv: -len(kv[0])):
        out = re.sub(rf"\b{re.escape(word)}\b",
                     f"{value:g}", out, flags=re.IGNORECASE)
    return out


def _expand_compact_numbers(text: str) -> str:
    """
    Turn '10k steps' into '10000 steps', and '10,000' into '10000'.

    Step counts are the one figure people almost always shorten, and they
    shorten it more when speaking than when typing, so anything arriving
    through the microphone has to survive it. Both forms used to fail,
    and both failed silently:

      "I walked 10k steps"  - no step rule matched '10k', so the exercise
                              rule matched the bare 10 and logged ten
                              minutes of walking.
      "10,000 steps"        - the number rule matched the '000' after the
                              comma and logged zero steps.

    A unit is only expanded when the k stands alone, so kg, km and kcal
    are left exactly as they are.
    """
    out = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)
    return re.sub(r"\b(\d+(?:\.\d+)?)\s*k\b",
                  lambda m: f"{float(m.group(1)) * 1000:g}", out)


def parse(text: str) -> dict:
    """Extract an intent and its entities from a user message."""
    raw = (text or "").strip()
    low = _expand_compact_numbers(_expand_word_numbers(raw.lower()))

    # A question about a number is not an instruction to log one.
    asking = any(neg in low for neg in _NEGATORS)

    # Keyword intents first - they carry no numbers to confuse things.
    for intent, phrases in KEYWORD_INTENTS:
        for phrase in phrases:
            if phrase in low:
                return {
                    "intent": intent,
                    "entities": {"text": raw},
                    "confidence": 0.9,
                    "matched": phrase,
                }

    if not asking:
        for intent, pattern, fields in PATTERNS:
            match = pattern.search(low)
            if not match:
                continue

            groups = [g for g in match.groups() if g is not None]
            if not groups:
                continue

            entities = {
                field: _to_number(value)
                for field, value in zip(fields, groups)
            }

            # Litres are stored as glasses.
            if intent == "log_water_litres":
                entities = {"water_glasses": round(entities["litres"] * 4)}
                intent = "log_water"

            if intent == "log_meal":
                entities["item"] = _meal_item(low) or "meal"

            return {
                "intent": intent,
                "entities": entities,
                "confidence": 0.85,
                "matched": match.group(0),
            }

    if asking:
        return {"intent": "question", "entities": {"text": raw},
                "confidence": 0.7, "matched": ""}

    return {"intent": "unknown", "entities": {"text": raw},
            "confidence": 0.0, "matched": ""}


def _meal_item(low: str) -> str:
    """Best-effort food name from a meal message."""
    cleaned = re.sub(
        r"\d+(\.\d+)?|kcal|calories|cals|cal\b|i ate|i had|logged?|log\b|"
        r"about|approx|roughly|around|for|with|of\b|\bwas\b|\bis\b|\bwere\b",
        " ", low)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-")
    return cleaned[:60]
