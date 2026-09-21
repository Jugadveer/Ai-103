"""
Symptom agent - the one that demonstrates cross-agent communication.

Flow:
  1. Safety check (red flags stop everything).
  2. Ask EVERY data-holding peer for its report via the bus.
  3. Look up general health information (RAG).
  4. Correlate peer data with the symptom and answer.

It never diagnoses. It explains likely contributing factors from the
user's own logged data and says when to see a doctor.
"""
from app.agents.base import BaseAgent, AgentReply
from app.core import logging as log
from app.services import safety
from app.services import health_ai
from app.services.search import lookup
from app.store import db

# Agents that hold no data of their own - asking them would add noise.
NON_DATA_AGENTS = ("coach", "insights", "report", "symptom")


class SymptomAgent(BaseAgent):
    name = "symptom"
    description = (
        "Discusses symptoms using general health information and correlates "
        "them with every other agent's data."
    )

    def handle(self, query: str) -> AgentReply:
        # 1. Safety first - before any model or peer call.
        verdict = safety.check(query)
        if not verdict["safe"]:
            log.warn("symptom_blocked", reason=verdict["reason"])
            return AgentReply(
                agent=self.name,
                text=verdict["message"],
                data={"blocked": True, "reason": verdict["reason"]},
            )

        db.add_symptom(query)

        # 2. Cross-agent communication: gather context from every peer.
        peers = self.bus.broadcast(self.name, reason=f"context for: {query}",
                                   exclude=NON_DATA_AGENTS) if self.bus else {}

        # 3. General health information about what they described.
        #    The local file is a fallback, not a ceiling: it holds six
        #    entries, so anything outside them used to return statistics
        #    at someone who had asked a question.
        kb = lookup(query)

        # 4. Correlate what the peers reported with the symptom.
        factors = self._contributing_factors(peers)
        log.info("symptom_analysed", peers=len(peers), factors=len(factors))

        return AgentReply(
            agent=self.name,
            text=self._compose(query, factors, kb, peers),
            data={"factors": factors, "peers": peers, "sources": kb},
        )

    def _contributing_factors(self, peers: dict) -> list[str]:
        """Turn peer reports into plain-language contributing factors."""
        found = []

        sleep = peers.get("sleep", {})
        if sleep.get("debt_hours", 0) >= 3:
            found.append(
                f"a sleep debt of about {sleep['debt_hours']} hours "
                f"(averaging {sleep.get('avg_hours')}h a night)")

        water = peers.get("hydration", {})
        if water.get("shortfall", 0) >= 3:
            found.append(
                f"low fluid intake - {water.get('glasses_today')} of "
                f"{water.get('target')} glasses today")

        food = peers.get("nutrition", {})
        if food.get("meals_today", 0) == 0:
            found.append("no meals logged today")
        elif food.get("status") == "low":
            found.append(
                f"a low calorie intake so far ({food.get('calories_today')} kcal)")

        move = peers.get("activity", {})
        if move.get("status") == "sedentary":
            found.append(
                f"very little movement this week "
                f"({move.get('minutes_week')} active minutes)")

        mood = peers.get("mood", {})
        if mood.get("status") == "low":
            found.append(
                f"a low mood score ({mood.get('avg_score')}/10 on average)")

        vitals = peers.get("vitals", {})
        if vitals.get("status") == "attention":
            found.append("a vitals reading outside the usual reference range")

        meds = peers.get("medication", {})
        if meds.get("status") == "missed":
            found.append(
                f"medication not yet taken today ({', '.join(meds['pending'])})")

        return found

    def _compose(self, query: str, factors: list[str], kb: list[dict],
                 peers: dict) -> str:
        parts = []
        if factors:
            parts.append(
                f"Looking at what you've logged, I can see {'; '.join(factors)}. "
                "Those are all common contributors to how you're feeling.")
        else:
            parts.append(
                "Your logged data all looks reasonable, so nothing there stands "
                "out as an obvious contributor.")

        # General information about the symptom itself. The model handles
        # anything, grounded in this person's own numbers; the local file
        # only covers six topics and takes over when we are offline.
        spoken = health_ai.answer(query, peers, domain="symptoms")
        if spoken:
            parts.append(spoken)
        elif kb:
            parts.append(kb[0]["content"])

        parts.append(
            "This is general information, not a diagnosis. If it persists, "
            "worsens, or you're worried, please see a doctor.")
        return " ".join(parts)

    def report(self) -> dict:
        rows = db.query("SELECT note, day FROM symptoms ORDER BY id DESC LIMIT 5")
        return {"recent_symptoms": [r["note"] for r in rows], "count": len(rows)}
