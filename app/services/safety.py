"""
Responsible-AI guardrails. Checked BEFORE any model or agent call.

Three layers, cheapest first:
  1. Red-flag terms  -> stop and tell the user to seek urgent care.
  2. Scope guard     -> refuse diagnosis / prescription requests.
  3. Azure AI Content Safety -> optional, for harmful content the lists miss.

Layers 1 and 2 are pure Python with no network dependency, so the
guardrails never fail open when Azure is unreachable.
"""
import re

from app import config
from app.core import logging as log

# Symptoms that need urgent care, not a chatbot.
RED_FLAGS = [
    # cardiac / respiratory
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
    "throat closing", "severe allergic reaction",
    "severe abdominal pain", "worst headache", "worst headache of my life",
    "high fever and stiff neck",
]

# Things this app must never do.
OUT_OF_SCOPE = [
    "diagnose me", "what disease do i have", "what condition do i have",
    "do i have cancer", "do i have diabetes", "am i dying",
    "prescribe", "what medicine should i take", "what medication should i take",
    "what dose", "dosage", "how many pills", "can i stop taking",
    "should i double", "is it safe to mix",
]

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
    "I'm not able to help with that. If you're struggling, please talk to "
    "someone you trust or a qualified professional."
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


def check(text: str) -> dict:
    """Return {'safe': bool, 'reason': str, 'matched': str, 'message': str}."""
    low = (text or "").lower()

    matched = _contains(low, RED_FLAGS)
    if matched:
        return {"safe": False, "reason": "red_flag", "matched": matched,
                "message": EMERGENCY_MESSAGE}

    matched = _contains(low, OUT_OF_SCOPE)
    if matched:
        return {"safe": False, "reason": "out_of_scope", "matched": matched,
                "message": SCOPE_MESSAGE}

    if content_safety_flags(text):
        return {"safe": False, "reason": "content_safety", "matched": "azure",
                "message": HARMFUL_MESSAGE}

    return {"safe": True, "reason": "", "matched": "", "message": ""}


def content_safety_available() -> bool:
    return not config.MOCK_MODE and bool(
        config.AZURE_CONTENT_SAFETY_KEY and config.AZURE_CONTENT_SAFETY_ENDPOINT)


def content_safety_flags(text: str, threshold: int = 4) -> bool:
    """
    Azure AI Content Safety check. Returns True if the text is harmful.

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
        worst = max((c.severity for c in result.categories_analysis), default=0)
        if worst >= threshold:
            log.warn("content_safety_flagged", severity=worst)
            return True
        return False
    except Exception as exc:
        log.warn("content_safety_unavailable", error=str(exc)[:120])
        return False
