"""
AgentBus - the message channel between agents.

Every agent-to-agent request goes through here and is recorded, so the UI
can show exactly which agents talked to which. That trace is the visible
proof of cross-agent communication.
"""
from datetime import datetime


class AgentBus:
    def __init__(self):
        self.agents: dict = {}
        self.trace: list[dict] = []
        # At most one open clarification across the whole system. See
        # app/core/dialog.py for why only one.
        self.pending = None

    def register(self, agent) -> None:
        agent.bus = self
        self.agents[agent.name] = agent

    def get(self, name: str):
        return self.agents.get(name)

    def request(self, sender: str, receiver: str, reason: str) -> dict:
        """One agent asks another for its report. Returns the peer's facts."""
        peer = self.agents.get(receiver)
        if peer is None:
            self._log(sender, receiver, reason, {"error": "no such agent"})
            return {}
        data = peer.safe_report()
        self._log(sender, receiver, reason, data)
        return data

    def broadcast(self, sender: str, reason: str,
                  exclude: tuple = ("coach",)) -> dict:
        """Ask every other specialist agent for its report at once.

        The orchestrator is excluded by default - it holds no domain data,
        so asking it would only add noise to the trace.
        """
        return {
            name: self.request(sender, name, reason)
            for name in self.agents
            if name != sender and name not in exclude
        }

    def _log(self, sender, receiver, reason, data) -> None:
        self.trace.append({
            "at": datetime.now().strftime("%H:%M:%S"),
            "from": sender,
            "to": receiver,
            "reason": reason,
            "data": data,
        })

    def reset_trace(self) -> None:
        self.trace = []

    # --- open clarifications -------------------------------------------

    def ask_followup(self, agent: str, kind: str, question: str,
                     context: dict | None = None):
        """An agent parks what it knows and waits for one more answer."""
        from app.core.dialog import Pending
        self.pending = Pending(agent=agent, kind=kind, question=question,
                               context=context or {})
        return self.pending

    def clear_followup(self) -> None:
        self.pending = None
