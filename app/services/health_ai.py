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
important to note that".

If the question has nothing at all to do with health, the body, food, \
sleep, movement, mood, or this person's own logged data, reply with \
exactly NOT_HEALTH and nothing else. Only for genuinely unrelated \
questions: anything a person might reasonably ask a wellness app is in \
scope, and a question about their own logged numbers always is."""

# The model's way of saying a question was not for it. Turned into a
# real sentence for the user rather than leaked out as a token.
OFF_TOPIC = "NOT_HEALTH"
OFF_TOPIC_REPLY = (
    "That one is outside what I do. I can help with sleep, food, water, "
    "movement, mood and how you have been feeling, and I can show you "
    "patterns in what you have logged."
)

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

    # Asked about something that is not health at all. Said plainly,
    # rather than routed to whichever agent the question least resembled
    # and answered with that agent's statistics.
    if reply.upper().startswith(OFF_TOPIC):
        return OFF_TOPIC_REPLY

    if FORBIDDEN.search(reply):
        log.warn("health_answer_blocked", snippet=reply[:90])
        return ""

    return reply


# Domains with a hand-written line above. Everything else is rendered
# generically by the loop at the end of _describe.
_DESCRIBED = ("sleep", "hydration", "nutrition", "activity", "mood", "vitals")


REFERRAL_PROMPT = """Someone has described how they feel and asked what is wrong with them. You must not tell them, and a bare refusal leaves them exactly where they started, which helps nobody.

Give them the most useful thing you can without naming anything:

- Which kind of clinician is the right one. Be specific where the description supports it: a dentist, a dermatologist, an eye specialist, a physiotherapist, a gynaecologist, an ENT specialist, a GP or family doctor when it could be several things, or emergency care when it sounds urgent.
- How soon. Today, within a few days, or at a routine appointment.
- What to bring or mention, if something specific would help them, such as how long it has gone on or what makes it worse.

Hard limits:
- Never name, suggest, hint at or rule out any condition or disease. Not even to reassure.
- Never mention medication, supplements or doses.
- Never say it is probably nothing or probably fine.
- Say plainly, once, that you cannot tell them what it is.

Three or four short sentences. Plain language. No lists, no headings."""


# Diagnosis as a sentence shape, not as a list of diseases.
#
# FORBIDDEN names about fifteen conditions. There are thousands, so a
# referral could sail past it with "this sounds like eczema" and that is
# a diagnosis however short the word is. What can be pinned down is the
# act: "sounds like X" is the same sentence whatever X is.
#
# This is deliberately strict, and only applied to referrals, where the
# expected answer is a clinician and a timeframe and none of these
# phrasings belong. Tripping it costs a nicer message and falls back to
# the plain refusal, so over-blocking here is cheap. That is the opposite
# of the general answer path, where over-blocking silently swallowed good
# answers and left people staring at statistics.
NAMING_A_CONDITION = re.compile(
    r"(?:sounds?|looks?|seems) like"
    r"|consistent with|indicative of|suggestive of|points? to"
    r"|\byou (?:may |might |probably )?have\b"
    r"|\b(?:could|might|may) be (?!worth|helpful|useful|a good|best)"
    r"|\bit(?:'s| is) (?:probably|likely|most likely)\b",
    re.IGNORECASE)


def referral(message: str) -> str:
    """
    What to do about it, when we will not say what it is.

    A refusal is not the same as being careful. Someone who asks what is
    wrong is asking because they are worried, and the honest useful
    answer is who should look at this and how soon, which is triage
    rather than diagnosis. The naming of a condition is the part a
    clinician has to do, and that stays refused.

    Returns '' when the model is unavailable or the reply crossed a line,
    so the caller can fall back to the plain refusal.
    """
    if not llm.available() or not (message or "").strip():
        return ""
    reply = llm.chat(REFERRAL_PROMPT, message.strip(), temperature=0.3)
    if not reply:
        return ""
    reply = reply.strip().strip('"')
    # Two guardrails: the shared one for medication and the named
    # conditions we know, and a stricter one for the act of naming
    # anything at all. A referral that names a condition is a diagnosis
    # wearing a hat.
    if FORBIDDEN.search(reply) or NAMING_A_CONDITION.search(reply):
        log.warn("referral_blocked", snippet=reply[:90])
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

    # Anything else gets a plain rendering rather than being dropped.
    #
    # The lines above cover the seven domains that hold data. The
    # meta-agents pass their own report instead, and every one of those
    # used to fall through this function and produce nothing, so the
    # model was asked "what is my streak" with no streak in front of it
    # and said it had no access to the data. It was right. Now an
    # unrecognised report is summarised generically, which also means the
    # next agent added works without editing this file.
    for name, report in (context or {}).items():
        if name in _DESCRIBED or not isinstance(report, dict):
            continue
        facts = [f"{k.replace('_', ' ')} {v}" for k, v in report.items()
                 if isinstance(v, (int, float, str)) and not isinstance(v, bool)
                 and k not in ("status", "has_data") and v != ""]
        if facts:
            lines.append(f"- {name}: " + ", ".join(facts[:8]))

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
