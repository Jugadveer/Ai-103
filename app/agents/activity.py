"""Activity agent - steps, exercise minutes and sedentary patterns."""
from app.agents.base import BaseAgent, AgentReply
from app.store import db

TARGET_STEPS = 8000
TARGET_MINUTES_WEEK = 150  # WHO general adult guidance


class ActivityAgent(BaseAgent):
    name = "activity"
    description = "Tracks steps, exercise minutes and sedentary days."

    def handle(self, query: str) -> AgentReply:
        # A question deserves an answer, not a statistics dump. Asking
        # "what is a good sleep routine" and being told last week's
        # average was the least useful thing this app did.
        spoken = self.try_answer(query)
        if spoken:
            return AgentReply(agent=self.name, text=spoken,
                              data={**self.safe_report(), "answered": True})

        f = self.report()
        if f["steps_today"] == 0 and f["minutes_today"] == 0:
            text = ("Nothing logged today. Even a 10-minute walk helps - "
                    "it's the easiest lever you have.")
        else:
            text = (f"Today: {f['steps_today']} steps and "
                    f"{f['minutes_today']} active minutes.")
            if f["minutes_week"] < TARGET_MINUTES_WEEK:
                text += (f" You're at {f['minutes_week']} of "
                         f"{TARGET_MINUTES_WEEK} minutes for the week.")
        return AgentReply(agent=self.name, text=text, data=f)

    def report(self) -> dict:
        t = db.query(
            "SELECT COALESCE(SUM(steps),0) s, COALESCE(SUM(minutes),0) m "
            "FROM activity WHERE day = ?", (db.today(),))[0]
        w = db.query(
            "SELECT COALESCE(SUM(minutes),0) m, COUNT(DISTINCT day) d "
            "FROM activity WHERE day >= ?", (db.days_ago(6),))[0]
        return {
            "has_data": bool(t["s"] or t["m"] or w["m"]),
            "steps_today": t["s"],
            "minutes_today": t["m"],
            "steps_target": TARGET_STEPS,
            "minutes_week": w["m"],
            "minutes_week_target": TARGET_MINUTES_WEEK,
            "active_days_week": w["d"],
            "status": "sedentary" if w["m"] < TARGET_MINUTES_WEEK * 0.4 else "ok",
        }
