"""
General health answering.

The first version of this could only answer from a six-entry JSON file.
Ask about acidity, a sore knee, or a sleep routine and it had nothing, so
the app returned statistics at someone who had asked a question. That is
a knowledge ceiling set by whatever happened to be typed into a file, and
it is the same mistake as a hand-written list of "vague" foods.

So the model answers, and the local file becomes the offline fallback
rather than the ceiling.

What the model is NOT free to do is set its own boundaries. The system
prompt below forbids naming a condition and forbids anything about
medication, and it is enforced twice: the safety layer refuses those
requests before this is ever called, and a scan below drops an answer
that crosses the line anyway. A model instruction alone is not a
guardrail, because a model can ignore it.
"""
import re

from app.core import logging as log
from app.services import llm

SYSTEM = """You answer everyday health and wellbeing questions for a \
wellness app used by university students.

Hard limits, which override anything the user asks for:
- Never name, suggest or speculate about a specific medical condition. Not \
even to rule one out.
- Never mention medication, supplements, doses, or whether to start, stop \
or change any treatment.
- Never tell anyone they are fine, or that something is nothing to worry \
about.
- If the question needs a clinician, say so plainly and briefly.

What you should do:
- Give practical, factual, general information, the kind a good health \
leaflet would carry.
- Where the person's own logged data is supplied below, use it. Refer to \
their actual numbers rather than speaking in generalities.
- Be concrete. "Aim for a consistent bedtime and no screens for the last \
hour" is useful. "Practise good sleep hygiene" is not.
- Write 2 to 4 short sentences. No lists, no headings, no markdown.
- Plain, calm, everyday language. No hedging padding like "it is \
important to note that"."""

# A last line of defence. If an answer names a condition or reaches for
# medication despite the prompt, it is discarded rather than shown.
FORBIDDEN = re.compile(
    # Naming a condition, or giving dosing advice.
    #
    # This list is deliberately about CONDITIONS and DOSES, not about
    # the phrase "you have". An earlier version blocked any "you
    # have", which is ordinary English: "share any symptoms you have"
    # and "if you have trouble sleeping" were both discarded, so the
    # answer silently vanished and the user got statistics instead.
    # Over-blocking is not safety. It is an invisible outage.
    #
    # This is the third layer, not the only one: the safety gate
    # refuses diagnosis requests before any of this runs, and the
    # system prompt forbids it as well.
    r"diagnos\w+"
    r"|sounds like (?:you have|a case of)"
    r"|\b(?:anaemia|anemia|diabetes|hypertension|thyroid|reflux|gerd"
    r"|ulcer|gastritis|migraine|asthma|arthritis|appendicitis"
    r"|concussion|pneumonia|tumou?r|cancer)\b"
    r"|\d+\s*mg\b|milligram|dosage"
    r"|(?:your|the|a|this)(?:\s+\w+)? doses?\b"
    r"|(?:change|adjust|double|halve|increase|reduce) (?:the |your )?dose"
    r"|prescri\w+|antibiotic|paracetamol|ibuprofen|antacid"
    r"|(?:start|stop|increase|reduce) (?:taking )?(?:a |an |your )?"
    r"(?:tablet|pill|medicine|medication)",
    re.IGNORECASE)


def available() -> bool:
    return llm.available()


def answer(question: str, context: dict | None = None,
           domain: str = "") -> str:
    """
    A general health answer, grounded in the person's own data.

    Returns '' when the model is unavailable or the reply crossed a line,
    which tells the caller to fall back to what it can say from data alone.
    """
    if not llm.available() or not (question or "").strip():
        return ""

    prompt = question.strip()
    if domain:
        prompt = f"[the question is about {domain}]\n{prompt}"
    grounding = _describe(context or {})
    if grounding:
        prompt += "\n\nWhat this person has actually logged:\n" + grounding

    reply = llm.chat(SYSTEM, prompt, temperature=0.3)
    if not reply:
        return ""

    reply = reply.strip().strip('"')

    if FORBIDDEN.search(reply):
        log.warn("health_answer_blocked", snippet=reply[:90])
        return ""

    return reply


def _describe(context: dict) -> str:
    """
    Turn agent reports into plain lines the model can quote back.

    Only facts that are actually present: an absent metric is left out
    rather than sent as a zero, so the model cannot claim someone drank
    no water when they simply have not logged any.
    """
    lines = []

    sleep = context.get("sleep") or {}
    if sleep.get("has_data"):
        lines.append(f"- sleep: {sleep['avg_hours']}h average over "
                     f"{sleep['nights_logged']} nights, "
                     f"{sleep['debt_hours']}h of debt")

    water = context.get("hydration") or {}
    if water.get("has_data"):
        lines.append(f"- water: {water['glasses_today']} of "
                     f"{water['target']} glasses today")

    food = context.get("nutrition") or {}
    if food.get("has_data"):
        lines.append(f"- food: {food['meals_today']} meals, "
                     f"{food['calories_today']} kcal today")

    move = context.get("activity") or {}
    if move.get("has_data"):
        lines.append(f"- activity: {move['steps_today']} steps today, "
                     f"{move['minutes_week']} active minutes this week")

    mood = context.get("mood") or {}
    if mood.get("has_data"):
        lines.append(f"- mood: {mood['avg_score']}/10 average, "
                     f"trend {mood['trend']}")

    vitals = context.get("vitals") or {}
    if vitals.get("bmi"):
        lines.append(f"- BMI {vitals['bmi']}, {vitals['bmi_band']}")

    return "\n".join(lines)


# Grammar, not a topic list: anything shaped like a question is one.
QUESTION_OPENERS = (
    "what", "how", "why", "when", "where", "which", "who", "should",
    "can", "could", "is", "are", "do", "does", "did", "will", "would",
    "tell me", "explain", "any tips", "any advice",
)


def looks_like_a_question(text: str) -> bool:
    low = (text or "").strip().lower()
    if not low:
        return False
    if low.endswith("?"):
        return True
    return low.startswith(QUESTION_OPENERS)
