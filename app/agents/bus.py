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
                  exclude: tuple | None = None) -> dict:
        """
        Ask every data-holding agent for its report at once.

        Who that is comes from each agent's own holds_data flag, not from
        a list kept here. Five copies of such a list existed once and
        three had gone stale, so the symptom agent was broadcasting to
        the meta-agents, which broadcast in turn: one question produced
        nineteen calls instead of eight.

        Pass exclude to override, which the check-in does to reach
        everything.
        """
        if exclude is None:
            audience = [n for n, a in self.agents.items() if a.holds_data]
        else:
            audience = [n for n in self.agents if n not in exclude]
        return {
            name: self.request(sender, name, reason)
            for name in audience
            if name != sender
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
