"""
Cross-agent communication - the headline behaviour of the project.

These tests assert that agents actually talk to each other through the bus,
that the trace records it, and that safety short-circuits before any of it.
"""
from app.store import db

DATA_PEERS = {"hydration", "nutrition", "sleep", "activity",
              "vitals", "mood", "medication"}


def test_symptom_queries_every_data_peer(seeded_bus):
    """One symptom question must fan out to all data-holding agents."""
    seeded_bus.get("coach").handle("I keep getting a headache in the afternoon")
    contacted = {e["to"] for e in seeded_bus.trace}
    assert DATA_PEERS.issubset(contacted), f"missed: {DATA_PEERS - contacted}"


def test_trace_records_sender_receiver_and_payload(seeded_bus):
    seeded_bus.get("coach").handle("I feel dizzy sometimes")
    hop = next(e for e in seeded_bus.trace if e["to"] == "sleep")
    assert hop["from"] == "symptom"
    assert "avg_hours" in hop["data"]
    assert hop["reason"]
    assert hop["at"]


def test_symptom_correlates_peer_data_into_factors(seeded_bus):
    reply = seeded_bus.get("coach").handle("I keep getting headaches")
    factors = " ".join(reply.data["factors"])
    assert "sleep debt" in factors
    assert "fluid" in factors
    assert reply.data["peers"]


def test_meta_agents_are_not_queried_for_data(seeded_bus):
    """insights/report/coach hold no data - asking them is noise."""
    seeded_bus.get("coach").handle("I have a mild headache")
    asked = {e["to"] for e in seeded_bus.trace if e["from"] == "symptom"}
    assert "insights" not in asked
    assert "report" not in asked
    assert "coach" not in asked


def test_insights_correlates_across_domains(seeded_bus):
    reply = seeded_bus.get("coach").handle("show me the patterns")
    patterns = reply.data["patterns"]
    assert patterns, "expected correlations from the seeded data"
    # every insight must cite the agents and evidence behind it
    for p in patterns:
        assert p["insight"] and p["evidence"] and p["agents"]


def test_insights_finds_the_sleep_mood_link(seeded_bus):
    reply = seeded_bus.get("coach").handle("what patterns do you see")
    joined = " ".join(p["insight"] for p in reply.data["patterns"]).lower()
    assert "mood" in joined and "sleep" in joined


def test_insights_says_so_when_there_is_nothing(bus):
    reply = bus.get("coach").handle("show me the patterns")
    assert reply.data["patterns"] == []
    assert "nothing stands out" in reply.text.lower()


def test_report_compiles_every_domain(seeded_bus):
    reply = seeded_bus.get("coach").handle("make a summary for my doctor")
    text = reply.text
    for heading in ["SLEEP", "FLUIDS", "DIET", "MOOD", "VITALS", "MEDS"]:
        assert heading in text, f"{heading} missing from the summary"
    assert "No diagnosis is implied" in text


def test_report_queries_all_peers(seeded_bus):
    seeded_bus.get("coach").handle("generate report")
    senders = {e["from"] for e in seeded_bus.trace}
    assert "report" in senders


def test_report_declines_when_data_is_thin(bus):
    reply = bus.get("coach").handle("make a summary for my doctor")
    assert "isn't enough logged" in reply.text


def test_checkin_collects_from_every_data_agent(seeded_bus):
    reply = seeded_bus.get("coach").handle("how am I doing today?")
    contacted = {e["to"] for e in seeded_bus.trace}
    assert DATA_PEERS.issubset(contacted)
    assert len(reply.text.splitlines()) >= 5


def test_emergency_short_circuits_before_any_peer_call(seeded_bus):
    """Nothing may run after a red flag - not routing, not peers."""
    reply = seeded_bus.get("coach").handle("I have chest pain and cannot breathe")
    assert reply.data.get("blocked") is True
    assert seeded_bus.trace == [], "agents were contacted after a red flag"


def test_trace_resets_between_requests(seeded_bus):
    seeded_bus.get("coach").handle("I have a headache")
    first = len(seeded_bus.trace)
    seeded_bus.reset_trace()
    assert seeded_bus.trace == []
    seeded_bus.get("coach").handle("I have a headache")
    assert len(seeded_bus.trace) == first


def test_adding_an_agent_extends_correlation_automatically(bus, clean_db):
    """A new agent joins every broadcast without editing the symptom agent."""
    from app.agents.base import AgentReply, BaseAgent

    class StressAgent(BaseAgent):
        name = "stress"
        description = "test agent"

        def handle(self, q):
            return AgentReply(agent=self.name, text="stressed")

        def report(self):
            return {"level": "high", "status": "low"}

    bus.register(StressAgent())
    bus.get("coach").handle("I feel unwell")
    assert "stress" in {e["to"] for e in bus.trace}


def test_no_agent_ever_queries_a_meta_agent_for_data(seeded_bus):
    """
    Regression: insights was querying `report`, which holds no data, adding
    a meaningless hop to the trace. No agent should ask a meta-agent for
    data - assert it for every entry point, not just the symptom agent.
    """
    meta = {"coach", "insights", "report"}
    for message in ["I keep getting headaches",      # -> symptom
                    "show me the patterns",          # -> insights
                    "make a summary for my doctor",  # -> report
                    "how am I doing today?"]:        # -> coach check-in
        seeded_bus.reset_trace()
        seeded_bus.get("coach").handle(message)
        bad = [f"{e['from']}->{e['to']}" for e in seeded_bus.trace
               if e["from"] != "coach" and e["to"] in meta]
        assert not bad, f"{message!r} produced meta-agent calls: {bad}"


def test_a_broadcast_reaches_only_data_holding_agents(bus):
    """
    Regression: the exclusion list was copied into five files and three
    went stale when new meta-agents were added. The symptom agent then
    broadcast to progress and assessment, which broadcast in turn, and
    one question produced nineteen calls instead of eight.
    """
    bus.reset_trace()
    bus.get("symptom").handle("I have a headache")
    reached = {e["to"] for e in bus.trace}
    for meta in ("coach", "progress", "assessment", "insights", "report"):
        assert meta not in reached, f"symptom broadcast to {meta}"


def test_the_headline_scenario_stays_at_eight_hops(seeded_bus):
    """The number quoted in the video script. It must not drift."""
    seeded_bus.reset_trace()
    seeded_bus.get("coach").handle("I keep getting a headache in the afternoon")
    assert len(seeded_bus.trace) == 8, \
        [f"{e['from']}->{e['to']}" for e in seeded_bus.trace]


def test_every_agent_declares_whether_it_holds_data(bus):
    holders = {n for n, a in bus.agents.items() if a.holds_data}
    assert holders == {"hydration", "nutrition", "sleep", "activity",
                       "vitals", "mood", "medication", "symptom"}


def test_a_meta_agent_does_not_cascade(seeded_bus):
    """insights asks the specialists, and none of them asks anyone back."""
    seeded_bus.reset_trace()
    seeded_bus.get("insights").handle("patterns")
    senders = {e["from"] for e in seeded_bus.trace}
    assert senders == {"insights"}
