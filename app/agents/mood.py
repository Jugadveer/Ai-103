"""
Mood agent - daily wellbeing score on a 1-10 scale.

Mood correlates strongly with sleep, so this agent is a frequent peer in
cross-agent reasoning. Anything suggesting self-harm is caught by the
safety layer before it ever reaches here.
"""
from app.agents.base import BaseAgent, AgentReply
from app.store import db


class MoodAgent(BaseAgent):
    name = "mood"
    description = "Tracks daily mood scores and wellbeing trends."

    def handle(self, query: str) -> AgentReply:
        f = self.report()
        if f["days_logged"] == 0:
            return AgentReply(
                agent=self.name,
                text="No mood logged yet. Tell me how you're feeling out of 10.",
                data=f,
            )
        text = (f"Your mood has averaged {f['avg_score']} out of 10 across "
                f"{f['days_logged']} days.")
        if f["trend"] == "falling":
            text += " It's been trending down over the last few days."
        elif f["trend"] == "rising":
            text += " It's been trending up - good."
        if f["status"] == "low":
            text += (" If low mood keeps up for more than two weeks, that's "
                     "worth talking to a doctor or counsellor about.")
        return AgentReply(agent=self.name, text=text, data=f)

    def report(self) -> dict:
        rows = db.query(
            "SELECT score, day FROM mood ORDER BY id DESC LIMIT 14")
        scores = [r["score"] for r in rows]
        n = len(scores)
        avg = round(sum(scores) / n, 1) if n else 0.0

        trend = "flat"
        if n >= 4:
            recent = sum(scores[:2]) / 2
            older = sum(scores[-2:]) / 2
            if recent < older - 1:
                trend = "falling"
            elif recent > older + 1:
                trend = "rising"

        return {
            "has_data": n > 0,
            "days_logged": n,
            "avg_score": avg,
            "today_score": scores[0] if n else None,
            "trend": trend,
            "status": "low" if n and avg <= 4 else "ok",
        }
