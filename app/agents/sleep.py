"""Sleep agent - tracks sleep hours and accumulated sleep debt."""
from app.agents.base import BaseAgent, AgentReply
from app.store import db

TARGET_HOURS = 8.0


class SleepAgent(BaseAgent):
    name = "sleep"
    description = "Tracks sleep duration, quality and sleep debt."

    def handle(self, query: str) -> AgentReply:
        f = self.report()
        text = (
            f"Over the last {f['nights_logged']} nights you averaged "
            f"{f['avg_hours']} hours."
        )
        if f["debt_hours"] > 0:
            text += f" That's a sleep debt of about {f['debt_hours']} hours."
        return AgentReply(agent=self.name, text=text, data=f)

    def report(self) -> dict:
        rows = db.query(
            "SELECT hours FROM sleep ORDER BY day DESC LIMIT 7"
        )
        hours = [r["hours"] for r in rows]
        nights = len(hours)
        avg = round(sum(hours) / nights, 1) if nights else 0.0
        debt = round(max(0.0, (TARGET_HOURS * nights) - sum(hours)), 1)
        return {
            "has_data": nights > 0,
            "nights_logged": nights,
            "avg_hours": avg,
            "target": TARGET_HOURS,
            "debt_hours": debt,
            "status": "poor" if nights and avg < 6.5 else "ok",
        }
