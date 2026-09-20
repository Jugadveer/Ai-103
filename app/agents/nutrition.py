"""Nutrition agent - tracks meals and calories."""
from app.agents.base import BaseAgent, AgentReply
from app.store import db

TARGET_CALORIES = 2000


class NutritionAgent(BaseAgent):
    name = "nutrition"
    description = "Tracks meals, calories and eating gaps."

    def handle(self, query: str) -> AgentReply:
        f = self.report()
        text = (
            f"You've logged {f['meals_today']} meals today, "
            f"about {f['calories_today']} calories."
        )
        if f["meals_today"] == 0:
            text = "Nothing logged today yet. Skipping meals will catch up with you."
        return AgentReply(agent=self.name, text=text, data=f)

    def report(self) -> dict:
        rows = db.query(
            "SELECT COUNT(*) AS n, COALESCE(SUM(calories), 0) AS cals "
            "FROM meals WHERE day = ?",
            (db.today(),),
        )
        n = rows[0]["n"] if rows else 0
        cals = rows[0]["cals"] if rows else 0
        return {
            "has_data": n > 0,
            "meals_today": n,
            "calories_today": cals,
            "target": TARGET_CALORIES,
            "status": "low" if cals < TARGET_CALORIES * 0.5 else "ok",
        }
