"""
The path that only runs when Azure is configured.

Every other suite runs in MOCK_MODE, where llm.available() is false and
try_answer returns immediately. That is most of the value of the tests
and it hid three bugs that only appeared in production: a meta-agent's
own report never reaching the model, every meta-agent gathering its
report twice per question, and nothing at all declining a question that
had no connection to health.

So these stub the model rather than disabling it. The stub records what
it was asked, which is the only way to check the model was actually
handed the numbers it is supposed to answer from.
"""
import pytest

from app.services import health_ai


class Stub:
    """Stands in for Azure. Records the prompt, returns what it is told."""

    def __init__(self, reply="A plain answer about sleep."):
        self.reply = reply
        self.prompts = []

    def chat(self, system, user, **kwargs):
        self.prompts.append(user)
        return self.reply

    @property
    def last(self):
        return self.prompts[-1] if self.prompts else ""


@pytest.fixture
def model(monkeypatch):
    stub = Stub()
    monkeypatch.setattr(health_ai.llm, "available", lambda: True)
    monkeypatch.setattr(health_ai.llm, "chat", stub.chat)
    return stub


# --- (1) the model must be given the numbers -----------------------------

def test_a_meta_agents_report_reaches_the_model(model, seeded_bus):
    """
    The bug: asked "what is my streak" with an 8-day streak on record,
    the deployed app replied that it had no access to streak data. It
    was telling the truth. _describe knew how to render the seven data
    domains and silently dropped everything else, so the model was given
    an empty grounding block.
    """
    seeded_bus.reset_trace()
    seeded_bus.get("progress").handle("what is my streak")

    assert model.prompts, "the model was never called"
    assert "progress" in model.last, \
        f"the progress report never reached the model:\n{model.last}"
    assert "streak" in model.last


def test_an_unknown_report_is_still_described():
    """A new agent should not have to edit health_ai to be understood."""
    grounding = health_ai._describe({
        "telepathy": {"has_data": True, "signal_strength": 7,
                      "last_reading": "strong"},
    })
    assert "telepathy" in grounding
    assert "signal strength 7" in grounding
    assert "last reading strong" in grounding


def test_the_hand_written_domains_still_win():
    """The generic fallback must not duplicate a domain that has a line."""
    grounding = health_ai._describe({
        "hydration": {"has_data": True, "glasses_today": 3, "target": 8},
    })
    assert grounding.count("hydration") + grounding.count("water") == 1
    assert "3 of 8 glasses today" in grounding


def test_booleans_are_not_read_out_as_facts():
    grounding = health_ai._describe({"progress": {"has_data": True,
                                                  "locked": True, "streak": 4}})
    assert "streak 4" in grounding
    assert "True" not in grounding


# --- (2) one question, one gathering -------------------------------------

@pytest.mark.parametrize("agent,expected", [
    ("progress", 8), ("insights", 8), ("report", 8),
])
def test_a_meta_agent_asks_its_peers_once(model, seeded_bus, agent, expected):
    """
    The bug: try_answer built its own copy of the report for grounding
    and the fallback path built another, so one question put 17 hops in
    the trace. The trace is what this project demonstrates, so a wrong
    number in it is not cosmetic.
    """
    seeded_bus.reset_trace()
    seeded_bus.get(agent).handle("how am I doing")
    hops = len(seeded_bus.trace)
    assert hops == expected, \
        f"{agent} made {hops} calls, expected {expected}: {seeded_bus.trace}"


def test_a_data_agent_asks_the_database_once_too(model, seeded_bus):
    seeded_bus.reset_trace()
    seeded_bus.get("hydration").handle("how much water should I drink")
    assert len(seeded_bus.trace) == 0        # holds its own data, asks nobody


# --- (3) declining what is not ours --------------------------------------

def test_an_unrelated_question_is_declined(monkeypatch):
    """
    The bug: "what is the capital of France" was routed to the mood
    agent, which answered with advice about low mood. The model is now
    asked to flag anything unrelated, and the flag becomes a sentence.
    """
    monkeypatch.setattr(health_ai.llm, "available", lambda: True)
    monkeypatch.setattr(health_ai.llm, "chat",
                        lambda system, user, **kw: "NOT_HEALTH")

    reply = health_ai.answer("what is the capital of France")
    assert reply == health_ai.OFF_TOPIC_REPLY
    assert "NOT_HEALTH" not in reply
    assert "sleep" in reply and "mood" in reply


def test_the_marker_never_leaks_even_with_trailing_text(monkeypatch):
    monkeypatch.setattr(health_ai.llm, "available", lambda: True)
    monkeypatch.setattr(health_ai.llm, "chat",
                        lambda system, user, **kw: "NOT_HEALTH.\nParis.")
    assert health_ai.answer("capital of France") == health_ai.OFF_TOPIC_REPLY


def test_a_health_question_is_not_declined(model):
    model.reply = "Aim for around eight glasses spread through the day."
    reply = health_ai.answer("how much water should I drink")
    assert reply == model.reply


def test_the_prompt_tells_the_model_to_flag_unrelated_questions():
    assert "NOT_HEALTH" in health_ai.SYSTEM
    # and not so eagerly that ordinary questions get caught
    assert "Only for genuinely unrelated" in health_ai.SYSTEM


# --- the guardrail still applies to model output -------------------------

def test_a_condition_named_by_the_model_is_still_discarded(monkeypatch):
    monkeypatch.setattr(health_ai.llm, "available", lambda: True)
    monkeypatch.setattr(
        health_ai.llm, "chat",
        lambda system, user, **kw: "This sounds like you have diabetes.")
    assert health_ai.answer("why am I thirsty") == ""


def test_the_off_topic_reply_is_not_itself_blocked():
    """It mentions nothing forbidden, but check rather than assume."""
    assert not health_ai.FORBIDDEN.search(health_ai.OFF_TOPIC_REPLY)
