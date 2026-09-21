"""
Medication agent - adherence tracking only.

It records what the user says they take and whether they took it today.
It never advises on drugs, doses, interactions or substitutions - those
requests are refused by the safety layer before reaching this agent.
"""
from app.agents.base import BaseAgent, AgentReply
from app.store import db


class MedicationAgent(BaseAgent):
    name = "medication"
    description = (
        "Tracks which medications the user has told us about and whether "
        "they have been taken today. Never advises on drugs or doses."
    )

    def handle(self, query: str) -> AgentReply:
        # A question deserves an answer, not a statistics dump. Asking
        # "what is a good sleep routine" and being told last week's
        # average was the least useful thing this app did.
        spoken = self.try_answer(query)
        if spoken:
            return AgentReply(agent=self.name, text=spoken,
                              data={**self.safe_report(), "answered": True})

        f = self.report()
        if f["tracked"] == 0:
            return AgentReply(
                agent=self.name,
                text=("You haven't added any medications yet. Tell me the name "
                      "and I'll remind you - though I can't advise on doses."),
                data=f,
            )
        if f["pending"]:
            text = (f"Still to take today: {', '.join(f['pending'])}. "
                    f"You've taken {f['taken_today']} of {f['tracked']}.")
        else:
            text = f"All {f['tracked']} medications logged as taken today."
        return AgentReply(agent=self.name, text=text, data=f)

    def report(self) -> dict:
        meds = db.query(
            "SELECT id, name FROM medications WHERE active = 1")
        taken_ids = {
            r["med_id"] for r in
            db.query("SELECT med_id FROM med_log WHERE day = ? AND taken = 1",
                     (db.today(),))
        }
        pending = [m["name"] for m in meds if m["id"] not in taken_ids]
        week = db.query(
            "SELECT COUNT(*) c FROM med_log WHERE day >= ? AND taken = 1",
            (db.days_ago(6),))[0]["c"]
        expected = len(meds) * 7
        return {
            "has_data": bool(meds),
            "tracked": len(meds),
            "names": [m["name"] for m in meds],
            "taken_today": len(meds) - len(pending),
            "pending": pending,
            "adherence_week_pct": round(100 * week / expected) if expected else 0,
            "status": "missed" if pending else "ok",
        }
