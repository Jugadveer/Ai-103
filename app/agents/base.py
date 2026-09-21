"""
Shared contract every specialist agent implements.

Two methods matter:
  handle(query)  - answer a question in this agent's domain
  report()       - hand a short factual summary to ANOTHER agent

report() is what makes cross-agent communication possible: the Symptom
agent never reads the sleep table directly, it asks the Sleep agent.

Both have a safe_* wrapper. One agent raising must never take down the
whole reply - the orchestrator degrades to a partial answer instead.
"""
from dataclasses import dataclass, field

from app.core import logging as log
from app.core.errors import HealthCoachError


@dataclass
class AgentReply:
    """What an agent sends back."""
    agent: str
    text: str
    data: dict = field(default_factory=dict)


class BaseAgent:
    name: str = "base"
    description: str = ""

    # Whether this agent owns a domain of its own data. Meta-agents set
    # this False: they hold nothing and work by asking the others, so
    # asking THEM for data is pointless and, worse, makes them broadcast
    # in turn. The bus reads this to decide who a broadcast reaches, which
    # is why it is declared here rather than kept as a list of names that
    # someone has to remember to update.
    holds_data: bool = True

    def __init__(self, bus=None):
        # The bus is how this agent reaches its peers.
        self.bus = bus

    # --- to be implemented by each agent -------------------------------

    def handle(self, query: str) -> AgentReply:
        raise NotImplementedError

    def report(self) -> dict:
        """Compact facts this agent is willing to share with other agents."""
        return {}

    # --- failure isolation ---------------------------------------------

    def safe_handle(self, query: str) -> AgentReply:
        """handle() that never raises."""
        try:
            return self.handle(query)
        except HealthCoachError as exc:
            log.warn("agent_rejected", agent=self.name, error=str(exc))
            return AgentReply(agent=self.name, text=exc.user_message,
                              data={"error": True})
        except Exception as exc:
            log.error("agent_crashed", agent=self.name, error=str(exc)[:200])
            return AgentReply(
                agent=self.name,
                text="I hit a problem working that out. Could you try again?",
                data={"error": True},
            )

    def safe_report(self) -> dict:
        """report() that never raises. Returns {} on failure."""
        try:
            return self.report()
        except Exception as exc:
            log.error("report_failed", agent=self.name, error=str(exc)[:200])
            return {"error": True, "status": "unavailable"}

    # --- answering questions --------------------------------------------

    def try_answer(self, query: str, context: dict | None = None) -> str:
        """
        Answer a question in this agent's domain, grounded in real data.

        Returns '' when the question is not a question, when the model is
        unavailable, or when the answer crossed a guardrail. The caller
        then falls back to reporting what it holds.
        """
        from app.services import health_ai
        if not health_ai.looks_like_a_question(query):
            return ""
        return health_ai.answer(query, context or {self.name: self.safe_report()},
                                domain=self.name)

    # --- peer access ----------------------------------------------------

    def ask_peer(self, peer_name: str, reason: str) -> dict:
        """Request another agent's report. Logged by the bus for the demo."""
        if self.bus is None:
            return {}
        return self.bus.request(self.name, peer_name, reason)
