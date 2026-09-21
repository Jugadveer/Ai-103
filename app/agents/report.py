"""
Report agent - builds a summary the user can take to a real doctor.

This is the responsible endpoint of the whole system: rather than trying to
answer a medical question itself, the app organises the user's own logged
data into something a clinician can read in thirty seconds.

It states facts and observations only. It draws no conclusions.
"""
from datetime import date

from app.agents.base import BaseAgent, AgentReply
from app.store import db



class ReportAgent(BaseAgent):
    name = "report"
    description = (
        "Compiles a factual health summary from every agent, formatted for "
        "the user to share with a clinician."
    )
    holds_data = False

    def handle(self, query: str) -> AgentReply:
        # A question about the subject deserves an answer, not this
        # agent's analysis. "Why do streaks help with habits" is not a
        # request for the current streak.
        spoken = self.try_answer(query)
        if spoken:
            return AgentReply(agent=self.name, text=spoken,
                              data={"answered": True})

        peers = self.bus.broadcast(
            self.name, reason="compiling health summary",
        ) if self.bus else {}
        text = self.build(peers)
        return AgentReply(agent=self.name, text=text,
                          data={"report": text, "peers": peers})

    def build(self, peers: dict) -> str:
        lines = [
            f"HEALTH SUMMARY - {date.today().strftime('%d %B %Y')}",
            "Self-reported data. Not a clinical record.",
            "",
        ]

        sleep = peers.get("sleep", {})
        if sleep.get("nights_logged"):
            lines.append(
                f"SLEEP    {sleep['avg_hours']}h average over "
                f"{sleep['nights_logged']} nights "
                f"(debt {sleep['debt_hours']}h)")

        water = peers.get("hydration", {})
        if water.get("has_data"):
            lines.append(
                f"FLUIDS   {water.get('glasses_today')} of "
                f"{water.get('target')} glasses today")

        food = peers.get("nutrition", {})
        if food.get("has_data"):
            lines.append(
                f"DIET     {food.get('meals_today')} "
                f"{'meal' if food.get('meals_today') == 1 else 'meals'}, "
                f"{food.get('calories_today')} kcal today")

        move = peers.get("activity", {})
        if move.get("minutes_week"):
            lines.append(
                f"ACTIVITY {move['minutes_week']} active minutes this week "
                f"across {move['active_days_week']} days")

        vit = peers.get("vitals", {})
        readings = []
        if vit.get("weight_kg"):
            readings.append(f"weight {vit['weight_kg']:g}kg")
        if vit.get("bmi"):
            readings.append(f"BMI {vit['bmi']}")
        if vit.get("heart_rate"):
            readings.append(f"HR {vit['heart_rate']:g}bpm")
        if vit.get("blood_pressure"):
            readings.append(f"BP {vit['blood_pressure']}")
        if readings:
            lines.append("VITALS   " + ", ".join(readings))

        # Energy requirement, when we hold enough to compute one. A
        # clinician reading this wants intake against requirement, not
        # intake alone.
        profile = db.get_profile()
        if vit.get("weight_kg") and vit.get("height_cm") and profile.get("age"):
            try:
                from app.core import energy
                needs = energy.maintenance(
                    vit["weight_kg"], vit["height_cm"], int(profile["age"]),
                    profile.get("sex", ""),
                    profile.get("activity_level", energy.DEFAULT_LEVEL))
                lines.append(
                    f"ENERGY   est. maintenance {needs['maintenance']} kcal/day "
                    f"({needs['range_low']}-{needs['range_high']}), "
                    f"Mifflin-St Jeor")
            except (ValueError, TypeError):
                pass

        md = peers.get("mood", {})
        if md.get("days_logged"):
            lines.append(
                f"MOOD     {md['avg_score']}/10 average, trend {md['trend']}")

        meds = peers.get("medication", {})
        if meds.get("tracked"):
            lines.append(
                f"MEDS     {', '.join(meds['names'])} - "
                f"{meds['adherence_week_pct']}% adherence this week")

        recent = db.query(
            "SELECT note, day FROM symptoms WHERE user_id = ? "
            "ORDER BY id DESC LIMIT 5", (db.current_user(),))
        if recent:
            lines.append("")
            lines.append("REPORTED SYMPTOMS")
            for r in recent:
                lines.append(f"  {r['day']}  {r['note']}")

        if len(lines) <= 3:
            return ("There isn't enough logged yet to build a useful summary. "
                    "Log a few days of sleep, meals and water first.")

        lines += [
            "",
            "All figures are self-reported by the patient. Nothing here was "
            "measured by a device. Calorie and energy figures are estimates.",
            "Prepared by a student wellness app. No diagnosis is implied and "
            "no clinician has reviewed this.",
        ]
        return "\n".join(lines)

    def report(self) -> dict:
        return {"role": "reporting", "holds_data": False}
