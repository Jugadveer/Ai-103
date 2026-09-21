"""
General health answering, and the guardrail on top of it.

These run in MOCK_MODE with no model, so what is pinned here is the
behaviour that has to hold without one: questions degrade to reported
data rather than erroring, and the guardrail regex itself is correct.
"""
import pytest

from app.services import health_ai


# --- is it a question at all ------------------------------------------

@pytest.mark.parametrize("text", [
    "what is a good sleep routine?",
    "how much protein do I need?",
    "why do I feel dizzy when I stand up",
    "should I drink more water",
    "any tips for sleeping better",
    "explain sleep debt",
])
def test_questions_are_recognised(text):
    assert health_ai.looks_like_a_question(text) is True


@pytest.mark.parametrize("text", [
    "I drank 3 glasses of water",
    "I slept 6 hours",
    "a big mac",
    "",
])
def test_statements_are_not_questions(text):
    assert health_ai.looks_like_a_question(text) is False


# --- the guardrail ----------------------------------------------------

@pytest.mark.parametrize("text", [
    "You probably have acid reflux.",
    "This sounds like a case of anaemia.",
    "You may have a thyroid problem.",
    "Take 400 mg of ibuprofen.",
    "The recommended dose is two tablets.",
    "I would prescribe an antacid.",
    "That is a classic sign of diabetes.",
])
def test_the_guardrail_catches_diagnosis_and_medication(text):
    assert health_ai.FORBIDDEN.search(text), f"got through: {text!r}"


@pytest.mark.parametrize("text", [
    "Aim for about 0.8 grams of protein per kilogram of body weight.",
    "Protein-rich foods like beans, eggs and nuts help you get there.",
    "Try a consistent bedtime and no screens for an hour before bed.",
    "Drink steadily through the day and watch the colour of your urine.",
    "Eating more slowly and sitting upright after meals often helps.",
    "Warming up properly and building distance gradually reduces strain.",
])
def test_the_guardrail_does_not_block_ordinary_advice(text):
    """
    Over-blocking is not safety, it is a broken feature: the answer
    silently disappears and the user gets statistics instead. An earlier
    version caught "supplement" and killed a good answer about protein.
    """
    assert not health_ai.FORBIDDEN.search(text), f"wrongly blocked: {text!r}"


def test_the_guardrail_has_no_stray_control_characters():
    """
    Regression: a patch turned every \\b word boundary into a literal
    backspace character, so the pattern silently matched nothing at all
    and the guardrail was doing no work.
    """
    assert chr(8) not in health_ai.FORBIDDEN.pattern
    assert "\\b" in health_ai.FORBIDDEN.pattern


# --- behaviour without a model ---------------------------------------

def test_answering_is_unavailable_without_a_model():
    assert health_ai.available() is False          # MOCK_MODE
    assert health_ai.answer("what is a good sleep routine?") == ""


def test_an_agent_falls_back_to_its_data_when_it_cannot_answer(bus, clean_db):
    """Offline, a question still gets a useful reply rather than an error."""
    from app.store import db
    db.add_sleep(6)
    reply = bus.get("sleep").handle("what is a good sleep routine?")
    assert reply.text
    assert reply.data.get("answered") is not True


def test_every_specialist_can_answer_questions(bus):
    """The capability has to be on all of them, not just the ones I tested."""
    for name in ("hydration", "nutrition", "sleep", "activity",
                 "vitals", "mood", "medication"):
        assert hasattr(bus.get(name), "try_answer"), name


def test_grounding_omits_metrics_with_no_data():
    """
    A missing metric must not be sent as a zero, or the model will tell
    someone they drank no water when they simply have not logged any.
    """
    described = health_ai._describe({
        "hydration": {"has_data": False, "glasses_today": 0, "target": 8},
        "sleep": {"has_data": True, "avg_hours": 5.4, "nights_logged": 7,
                  "debt_hours": 18.3},
    })
    assert "sleep" in described
    assert "water" not in described


def test_grounding_is_empty_when_nothing_is_logged():
    assert health_ai._describe({}) == ""


# --- the local file is a fallback, not the ceiling -------------------

def test_the_local_knowledge_base_is_only_a_fallback(bus, clean_db):
    """
    The six-entry file used to be the only source of health information,
    which meant anything outside it returned statistics at a question.
    It is still there for offline use, but the symptom agent no longer
    depends on it.
    """
    from app.services.search import lookup

    # Worse than returning nothing: keyword matching returns something
    # irrelevant. Asking about acidity matches an entry about skipped
    # meals, purely on the word "meals".
    hits = lookup("acidity after meals")
    assert not any("acid" in h["title"].lower() for h in hits), \
        "the file has no entry about acidity, so nothing should claim to"

    reply = bus.get("coach").handle("I keep getting acidity after meals")
    assert reply.text                                # still answers
    assert "not a diagnosis" in reply.text


# --- the guardrail must not eat ordinary English ---------------------

@pytest.mark.parametrize("text", [
    "Share any symptoms you have, and how long they have lasted.",
    "If you have trouble sleeping, keep the room dark and cool.",
    "Taking it at the same time keeps a steady level between doses.",
    "Aim for at least 150 minutes of moderate activity each week.",
    "A good sleep routine means going to bed at the same time daily.",
])
def test_ordinary_phrasing_is_not_blocked(text):
    """
    Regression, and the worst kind: an over-broad rule silently discarded
    four perfectly good answers, and the user just saw statistics. The
    phrase "you have" is ordinary English, not a diagnosis. What makes a
    diagnosis is naming a condition.
    """
    assert not health_ai.FORBIDDEN.search(text), f"wrongly blocked: {text!r}"


@pytest.mark.parametrize("text", [
    "You probably have acid reflux.",
    "That is a classic sign of diabetes.",
    "You may have a thyroid problem.",
    "The recommended dose is two tablets.",
    "You should stop taking your medication.",
])
def test_conditions_and_dosing_are_still_caught(text):
    assert health_ai.FORBIDDEN.search(text), f"got through: {text!r}"


def test_every_agent_can_answer_a_question(bus):
    """All thirteen, including the meta-agents that hold no data."""
    for name in bus.agents:
        if name == "coach":
            continue
        assert hasattr(bus.get(name), "try_answer"), name
