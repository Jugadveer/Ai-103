"""
Responsible-AI guardrails. Checked BEFORE any model or agent call.

Four layers, cheapest first:
  1. Red-flag terms  -> stop and tell the user to seek urgent care.
  2. Scope guard     -> refuse diagnosis / prescription requests.
  3. Model triage    -> the phrasings a written list was never going to have.
  4. Azure AI Content Safety -> harmful content the rest missed.

Layers 1 and 2 are pure Python with no network dependency, so the
guardrails never fail open when Azure is unreachable. Layers 3 and 4 can
only add a block, never lift one, which is what makes it safe to let a
model participate in a safety decision at all.

Layer 3 exists because layers 1 and 2 are literal. "chest pain" was
listed and "heart attack" was not, so "I think I am having a heart
attack" was answered with a correlation of the person's sleep and water
intake. Writing "heart attack" into the list fixes that sentence and
nothing else.
"""
import re

from app import config
from app.core import logging as log

# Symptoms that need urgent care, not a chatbot.
RED_FLAGS = [
    # cardiac / respiratory
    "heart attack", "cardiac arrest", "crushing chest",
    "chest pain", "chest tightness", "chest pressure", "can't breathe",
    "cannot breathe", "shortness of breath", "difficulty breathing",
    "struggling to breathe", "gasping",
    # mental health crisis
    "suicide", "suicidal", "kill myself", "end my life", "self harm",
    "self-harm", "want to die", "hurt myself",
    # bleeding / trauma
    "severe bleeding", "bleeding heavily", "won't stop bleeding",
    "coughing blood", "vomiting blood", "blood in my stool",
    # neurological
    "unconscious", "passed out", "fainted", "seizure", "convulsion",
    "stroke", "slurred speech", "face drooping", "numb on one side",
    "can't move my arm", "sudden confusion",
    # other emergencies
    "overdose", "poisoned", "swallowed pills", "anaphylaxis",
    "too many pills", "too many tablets", "took the whole bottle",
    "throat closing", "severe allergic reaction",
    "severe abdominal pain", "worst headache", "worst headache of my life",
    "high fever and stiff neck",
]

# Things this app must never do.
OUT_OF_SCOPE = [
    "diagnose me", "diagnose my", "what disease do i have",
    "what condition do i have", "what is wrong with me",
    "whats wrong with me", "what do i have",
    "do i have cancer", "do i have diabetes", "am i dying",
    "prescribe", "what medicine should i take", "what medication should i take",
    "what dose", "dosage", "how many pills", "can i stop taking",
    "should i double", "is it safe to mix",
]

# Which of the out-of-scope terms are someone asking what is wrong with
# them, as opposed to asking about medication. The first group gets
# referral guidance; the second gets a plain no.
DIAGNOSIS_TERMS = {t for t in OUT_OF_SCOPE
                   if any(w in t for w in ("diagnos", "disease", "condition",
                                           "wrong with me", "do i have",
                                           "am i dying"))}

EMERGENCY_MESSAGE = (
    "This sounds like it may need urgent medical attention. Please contact "
    "emergency services or get to the nearest hospital now. In India, dial 112 "
    "(emergency) or 108 (ambulance). I'm not able to help with this myself."
)

SCOPE_MESSAGE = (
    "I can't diagnose conditions or advise on medication - that needs a "
    "qualified clinician. What I can do is share general wellness information "
    "and show you patterns in what you've logged."
)

HARMFUL_MESSAGE = (
    "I'm not able to help with that one. If it is about medication or a "
    "dose, a pharmacist or doctor is the right person to ask."
)

# A dosage question used to land on the message above, which talks about
# struggling and reads as though the app thinks you are in crisis for
# asking how much paracetamol to take. Wrong answers to the wrong
# question look like a broken app even when nothing unsafe happened.
MEDICATION_MESSAGE = (
    "I can't advise on medication, doses or whether to start or stop "
    "anything. A pharmacist or doctor can, and a pharmacist is usually "
    "quick to reach. I can keep track of whether you have taken something, "
    "and nothing more than that."
)

# Caught here rather than in whichever agent the router happened to pick.
# "Write me a python function" reached the nutrition agent, which had no
# food to find and replied "Nothing logged, tell me what you ate."
# Deciding a message is not ours is a job for the layer that sees every
# message, not for the one that was guessed at.
OFF_TOPIC_MESSAGE = (
    "That one is outside what I do. I can help with sleep, food, water, "
    "movement, mood and how you have been feeling, and I can show you "
    "patterns in what you have logged."
)

CRISIS_MESSAGE = (
    "I'm sorry you're feeling like this, and I'm not the right kind of help. "
    "Please talk to someone now: Tele-MANAS, India's free 24/7 mental health "
    "helpline, is 14416, and emergency services are 112. If you can, tell "
    "someone near you how you are feeling."
)


# People insert filler inside a phrase: "face drooping" is also said as
# "face is drooping", "throat closing" as "throat is closing up". A safety
# list that only matches adjacent words misses those, so multi-word terms
# are compiled to tolerate a few filler words in between.
_FILLER = (r"(?:\s+(?:is|are|was|were|been|being|feels?|felt|got|getting|"
           r"keeps?|started|suddenly|really|very|so|my|the|a)){0,3}\s+")

_COMPILED: dict[str, re.Pattern] = {}


def _compile(term: str) -> re.Pattern:
    """Word-boundary regex; multi-word terms tolerate inserted filler."""
    if term not in _COMPILED:
        words = term.split()
        if len(words) == 1:
            pattern = rf"\b{re.escape(term)}\b"
        else:
            pattern = r"\b" + _FILLER.join(re.escape(w) for w in words)
        _COMPILED[term] = re.compile(pattern)
    return _COMPILED[term]


def _contains(text: str, terms: list[str]) -> str:
    """Return the first matching term, or ''. Word-aware to avoid false hits."""
    for term in terms:
        if _compile(term).search(text):
            return term
    return ""


TRIAGE_PROMPT = """You are a safety check on a student wellness app. \
Classify the message. Reply with ONE word and nothing else.

EMERGENCY - a physical situation needing urgent care now: cardiac, \
breathing, stroke signs, severe bleeding, poisoning, taking too much of \
something, collapse, anaphylaxis.
CRISIS - the person may harm themselves, or does not want to be alive.
DIAGNOSIS - asking what condition or disease they have, or to be told \
what is wrong with them.
MEDICATION - asking about medicines, doses, or starting or stopping a \
treatment.
OFF_TOPIC - nothing to do with health, the body, food, sleep, movement, \
mood or wellbeing. Coding, homework, geography, trivia, small talk.
OK - anything else, including ordinary symptoms, tiredness, logging food \
or sleep, and general health questions.

Lean towards OK. A mild sore throat, feeling tired, a headache or a bad \
mood are all OK: this app is for exactly those. Reserve the other five \
for messages that plainly match them."""

# Each verdict the model can return, and what the user is told.
TRIAGE = {
    "EMERGENCY": ("red_flag", EMERGENCY_MESSAGE),
    "CRISIS": ("self_harm", CRISIS_MESSAGE),
    "DIAGNOSIS": ("out_of_scope", SCOPE_MESSAGE),
    "MEDICATION": ("medication", MEDICATION_MESSAGE),
    "OFF_TOPIC": ("off_topic", OFF_TOPIC_MESSAGE),
}


def triage(text: str) -> dict | None:
    """
    Ask the model whether the lists missed something.

    Only ever returns a block or None, so this layer cannot make the app
    less careful than the lists already made it. If the model is not
    configured or the call fails, the answer is None and the local layers
    stand on their own.
    """
    from app.services import llm
    if not llm.available():
        return None
    try:
        reply, reason = llm.chat_with_reason(TRIAGE_PROMPT, text)
    except Exception as exc:
        log.warn("triage_unavailable", error=type(exc).__name__)
        return None

    if reason == "content_filter":
        # Azure would not even classify it. That is a verdict of its own,
        # and the safe reading is that the message was sensitive rather
        # than that the service was down. Neutral wording, because we do
        # not know which way it was sensitive.
        log.warn("triage_filtered")
        return {"safe": False, "reason": "content_filter",
                "matched": "azure:prompt_filter", "message": HARMFUL_MESSAGE}
    if reason != "ok":
        return None

    verdict = (reply or "").strip().upper()

    for name, (reason, message) in TRIAGE.items():
        if verdict.startswith(name):
            if name == "DIAGNOSIS":
                message = _referral_or_refusal(text)
            return {"safe": False, "reason": reason, "matched": f"model:{name}",
                    "message": message}
    return None


def _referral_or_refusal(text: str) -> str:
    """
    Point them at the right clinician instead of just saying no.

    Refusing to name a condition is correct. Stopping there is not
    useful: someone asking what is wrong is worried, and the thing they
    actually need is who should look at it and how soon. That is triage,
    not diagnosis, and it is the most helpful thing this app can honestly
    say. If the model cannot produce one, the plain refusal stands.
    """
    from app.services import health_ai
    try:
        guidance = health_ai.referral(text)
    except Exception as exc:
        log.warn("referral_unavailable", error=type(exc).__name__)
        return SCOPE_MESSAGE
    return guidance or SCOPE_MESSAGE


def check(text: str, deep: bool = False) -> dict:
    """
    Return {'safe': bool, 'reason': str, 'matched': str, 'message': str}.

    Layers 1 and 2 (red flags, scope) are local and ALWAYS run - they cost
    nothing and are the ones that matter clinically.

    Layers 3 and 4 (model triage, then Azure Content Safety) each cost a
    network round trip, so they run only when deep=True: for free text the
    parser could not classify, which is the only place an unrecognised
    emergency can hide. A recognised "I drank 3 glasses" needs neither,
    and paying for them would make every interaction sluggish.

    Note the ordering. The local layers run first and unconditionally, so
    the app is exactly as safe with the network down as with it up. The
    remote layers can only add blocks, never remove one.
    """
    low = (text or "").lower()

    matched = _contains(low, RED_FLAGS)
    if matched:
        return {"safe": False, "reason": "red_flag", "matched": matched,
                "message": EMERGENCY_MESSAGE}

    matched = _contains(low, OUT_OF_SCOPE)
    if matched:
        # A request to diagnose gets pointed at the right clinician. A
        # request about medication does not, because there is no useful
        # version of that answer from an app.
        message = (_referral_or_refusal(text) if matched in DIAGNOSIS_TERMS
                   else MEDICATION_MESSAGE)
        return {"safe": False, "reason": "out_of_scope", "matched": matched,
                "message": message}

    if deep:
        # The lists found nothing. Ask the model before deciding this is
        # ordinary, because the lists only know the words we thought of.
        verdict = triage(text)
        if verdict:
            log.warn("triage_block", matched=verdict["matched"])
            return verdict

    if deep:
        category = content_safety_flags(text)
        if category:
            # Self-harm gets the crisis message and a helpline. Anything
            # else gets a plain refusal, because telling someone who asked
            # about a dose that help is available reads as a non sequitur.
            crisis = "selfharm" in category.lower()
            return {"safe": False, "reason": "content_safety",
                    "matched": f"azure:{category}",
                    "message": CRISIS_MESSAGE if crisis else HARMFUL_MESSAGE}

    return {"safe": True, "reason": "", "matched": "", "message": ""}


def content_safety_available() -> bool:
    return not config.MOCK_MODE and bool(
        config.AZURE_CONTENT_SAFETY_KEY and config.AZURE_CONTENT_SAFETY_ENDPOINT)


def content_safety_flags(text: str, threshold: int = 4) -> str:
    """
    Azure AI Content Safety check. Returns the worst category it flagged,
    or "" for nothing. Truthy either way, so `if content_safety_flags(x)`
    reads the same as it always did.

    It returns the category rather than a bare yes, because the category
    decides what the user is told. "How many mg of paracetamol should I
    take" trips the self-harm classifier, which is reasonable of it, and
    the single message this used to return said "if you are struggling,
    please talk to someone you trust". Answering a dosage question that
    way is its own kind of wrong.

    Fails CLOSED-ish by design: if the service is unreachable we return
    False (not harmful) because layers 1 and 2 have already run and a
    network blip must not block a legitimate wellness question.
    """
    if not content_safety_available():
        return False

    try:
        from azure.ai.contentsafety import ContentSafetyClient
        from azure.ai.contentsafety.models import AnalyzeTextOptions
        from azure.core.credentials import AzureKeyCredential

        from app.core.retry import with_retry

        client = ContentSafetyClient(
            endpoint=config.AZURE_CONTENT_SAFETY_ENDPOINT,
            credential=AzureKeyCredential(config.AZURE_CONTENT_SAFETY_KEY),
        )
        result = with_retry(
            lambda: client.analyze_text(AnalyzeTextOptions(text=text)),
            label="content_safety",
        )
        worst = max(result.categories_analysis,
                    key=lambda c: c.severity, default=None)
        if worst is not None and worst.severity >= threshold:
            log.warn("content_safety_flagged", severity=worst.severity,
                     category=str(worst.category))
            return str(worst.category)
        return ""
    except Exception as exc:
        log.warn("content_safety_unavailable", error=str(exc)[:120])
        return ""
