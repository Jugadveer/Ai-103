"""Hydration agent - tracks water intake and reports it to peers."""
from app.agents.base import BaseAgent, AgentReply
from app.store import db

TARGET_GLASSES = 8


class HydrationAgent(BaseAgent):
    name = "hydration"
    description = "Tracks daily water intake and flags dehydration."

    def handle(self, query: str) -> AgentReply:
        # A question deserves an answer, not a statistics dump. Asking
        # "what is a good sleep routine" and being told last week's
        # average was the least useful thing this app did.
        spoken = self.try_answer(query)
        if spoken:
            return AgentReply(agent=self.name, text=spoken,
                              data={**self.safe_report(), "answered": True})

        facts = self.report()
        text = (
            f"You've had {facts['glasses_today']} of {TARGET_GLASSES} glasses today."
        )
        if facts["shortfall"] > 0:
            text += f" You're {facts['shortfall']} short - try one glass now."
        else:
            text += " You've hit your target. Nice."
        return AgentReply(agent=self.name, text=text, data=facts)

    def report(self) -> dict:
        rows = db.query(
            "SELECT COALESCE(SUM(glasses), 0) AS total FROM water WHERE day = ?",
            (db.today(),),
        )
        total = rows[0]["total"] if rows else 0
        return {
            "has_data": total > 0,
            "glasses_today": total,
            "target": TARGET_GLASSES,
            "shortfall": max(0, TARGET_GLASSES - total),
            "status": "low" if total < TARGET_GLASSES * 0.6 else "ok",
        }
