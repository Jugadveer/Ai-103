"""
Mood agent - daily wellbeing, self-reported.

Mood cannot be measured by a phone. No sensor reads it, and anything
claiming to infer it from typing speed or tone is guessing. So this agent
asks, on a plain one-to-ten scale with worded anchors so the number means
roughly the same thing from one day to the next. That is how mood is
captured clinically too: the person reports it.

Mood tracks strongly with sleep, which makes this a frequent peer in
cross-agent reasoning. Anything suggesting self-harm is caught by the
safety layer before it ever reaches this agent.
"""
from app.agents.base import BaseAgent, AgentReply
from app.store import db


# Anchors, so a 4 means something comparable from one week to the next.
SCALE = {
    1: "At my worst", 2: "Very low", 3: "Low", 4: "Below par",
    5: "Neutral", 6: "Reasonable", 7: "Good", 8: "Really good",
    9: "Excellent", 10: "At my best",
}


class MoodAgent(BaseAgent):
    name = "mood"
    description = (
        "Tracks self-reported daily mood on a 1-10 scale with worded "
        "anchors. Measures nothing: mood cannot be sensed, only reported."
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
        if f["days_logged"] == 0:
            return AgentReply(
                agent=self.name,
                text="No mood logged yet. I cannot sense how you feel, so "
                     "you have to tell me: where are you on a 1 to 10, "
                     "where 5 is neutral and 8 is really good?",
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
            "SELECT score, day FROM mood WHERE user_id = ? "
            "ORDER BY id DESC LIMIT 14", (db.current_user(),))
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

        today_score = scores[0] if n else None
        return {
            "has_data": n > 0,
            "self_reported": True,     # mood cannot be measured, only asked
            "scale": SCALE,
            "today_label": SCALE.get(int(today_score)) if today_score else None,
            "days_logged": n,
            "avg_score": avg,
            "today_score": scores[0] if n else None,
            "trend": trend,
            "status": "low" if n and avg <= 4 else "ok",
        }
