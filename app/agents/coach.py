"""
Coach agent - the orchestrator the user actually talks to.

Pipeline for every message:
  1. Safety check      - red flags and out-of-scope requests stop here
  2. Intent parsing    - deterministic patterns, no model call needed
  3. Logging           - validated writes, with a readable error if rejected
  4. Delegation        - route to the specialist, or fan out to all of them

The language model is only consulted when the deterministic parser has low
confidence, which keeps the common path free, instant and repeatable.
"""
import re

from app.agents.base import BaseAgent, AgentReply
from app.core import logging as log
from app.core import nlu
from app.core.errors import ValidationError
from app.services import llm, safety
from app.store import db

# Domain keywords used when the parser cannot classify a message.
ROUTES = {
    "hydration": ["water", "drink", "drank", "thirsty", "hydrate", "glass",
                  "fluid", "dehydrated"],
    "sleep": ["sleep", "slept", "tired", "insomnia", "rest", "nap", "awake",
              "bed", "drowsy", "exhausted"],
    "nutrition": ["eat", "ate", "meal", "food", "calorie", "lunch", "dinner",
                  "breakfast", "snack", "hungry", "diet", "protein",
                  "drank", "drink", "plate", "bowl", "portion", "serving"],
    "activity": ["exercise", "workout", "steps", "walk", "run", "gym", "yoga",
                 "active", "sedentary", "cycling", "swim"],
    "vitals": ["weight", "bmi", "blood pressure", "heart rate", "pulse",
               "bp", "height", "kg", "bpm"],
    "mood": ["mood", "stressed", "anxious", "sad", "low", "happy", "wellbeing",
             "mental", "overwhelmed", "lonely"],
    "medication": ["medication", "medicine", "pill", "tablet", "dose",
                   "prescription", "adherence"],
    "progress": ["streak", "progress", "achievement", "badge", "ring",
                 "level", "points", "goal"],
    "assessment": ["maintenance", "tdee", "overeating", "undereating",
                   "deficit", "surplus", "energy needs", "assessment"],
    "symptom": ["headache", "pain", "ache", "dizzy", "nausea", "fever", "sick",
                "symptom", "unwell", "hurts", "cramp", "sore", "cough"],
}

# Complaints are recognised by sentence shape, not by a list of
# conditions. "I keep getting acidity after meals" is a complaint
# whatever the ailment is called, and no list of symptoms I write will
# ever cover every way of describing one. Used only offline; when the
# model is available it routes instead.
COMPLAINT_SHAPES = [re.compile(p) for p in (
    r"\bi (?:keep|kept) (?:getting|having|feeling)\b",
    r"\bmy \w+ (?:hurts|aches|is sore|feels|is killing)\b",
    r"\bi (?:feel|felt|am feeling) \w+",
    r"\b(?:pain|ache|aching|soreness) (?:in|around|near)\b",
    r"\bit (?:hurts|aches)\b",
    r"\bnot feeling (?:well|great|good)\b",
)]

ROUTER_PROMPT = "\n".join([
    "Route a health app message to ONE agent. Reply with the agent name "
    "alone, nothing else.",
    "hydration - drinking water, thirst",
    "nutrition - food eaten, meals, calories, diet questions",
    "sleep - sleeping, tiredness, rest",
    "activity - exercise, steps, movement",
    "vitals - weight, height, BMI, blood pressure, heart rate",
    "mood - feelings, stress, wellbeing",
    "medication - pills and whether they were taken",
    "symptom - any physical complaint, pain, discomfort or illness, "
    "including ones that mention food or meals",
])

HELP_TEXT = (
    "I coordinate a team of agents for you. You can:\n"
    "  - log things: \"I slept 6 hours\", \"drank 3 glasses\", "
    "\"walked 5000 steps\", \"mood is 7/10\"\n"
    "  - ask how you're doing: \"how am I doing today?\"\n"
    "  - look for patterns: \"show me the patterns\"\n"
    "  - describe a symptom: \"I keep getting headaches\"\n"
    "  - build a doctor summary: \"make a summary for my doctor\"\n"
    "I'm a wellness coach, not a doctor - I never diagnose."
)

# intent -> (agent that owns it, db writer, entity key, confirmation template)
LOG_ACTIONS = {
    "log_water": ("hydration", db.add_water, "water_glasses",
                  "Logged {v:g} glasses of water."),
    "log_sleep": ("sleep", db.add_sleep, "sleep_hours",
                  "Logged {v:g} hours of sleep."),
    "log_steps": ("activity", None, "steps", "Logged {v:g} steps."),
    "log_exercise": ("activity", None, "exercise_mins",
                     "Logged {v:g} minutes of activity."),
    "log_mood": ("mood", db.add_mood, "mood_score",
                 "Logged your mood at {v:g} out of 10."),
    "log_vital_weight": ("vitals", None, "weight_kg", "Logged weight {v:g} kg."),
    "log_vital_height": ("vitals", None, "height_cm", "Logged height {v:g} cm."),
    "log_vital_hr": ("vitals", None, "heart_rate",
                     "Logged heart rate {v:g} bpm."),
}


class CoachAgent(BaseAgent):
    name = "coach"
    description = "Orchestrator. Talks to the user and delegates to specialists."
    holds_data = False

    def handle(self, query: str) -> AgentReply:
        low = (query or "").lower().strip()
        if not low:
            return AgentReply(agent=self.name,
                              text="Tell me how you're doing and I'll help.")

        # 1. Safety gate on everything the user says. The local layers always
        #    run; the Azure Content Safety layer is added further down, once we
        #    know the message is free text rather than a recognised log command.
        verdict = safety.check(query)
        if not verdict["safe"]:
            log.warn("safety_block", reason=verdict["reason"],
                     matched=verdict["matched"])
            return AgentReply(
                agent=self.name,
                text=verdict["message"],
                data={"blocked": True, "reason": verdict["reason"]},
            )

        # 2. An open clarification takes priority: the user is answering a
        #    question, so the words mean something different than they would
        #    on their own. Safety has already run above, which is the point
        #    of doing this after the gate and not before it.
        pending = self.bus.pending if self.bus else None
        if pending is not None:
            owner = self.bus.get(pending.agent)
            if owner is not None and hasattr(owner, "continue_dialog"):
                pending.turns += 1
                self.bus.handoff(self.name, pending.agent,
                                 reason=f"answer to: {pending.question[:60]}")
                answered = owner.continue_dialog(query, pending.context)
                # None means the agent judged this a change of subject, so
                # the message is routed fresh rather than forced into it.
                if answered is not None:
                    return answered
                self.bus.clear_followup()
            self.bus.clear_followup()

        # 3. Deterministic intent parsing.
        parsed = nlu.parse(query)
        intent = parsed["intent"]
        log.info("intent", intent=intent, confidence=parsed["confidence"])

        # 4. Direct intents.
        if intent == "help":
            return AgentReply(agent=self.name, text=HELP_TEXT)

        if intent in LOG_ACTIONS:
            return self._do_log(intent, parsed)

        if intent == "log_vital_bp":
            return self._log_bp(parsed)

        if intent == "log_meal":
            # Delegated, not written here: the nutrition agent may want to
            # ask a question before it commits anything.
            return self._delegate("nutrition", query)

        if intent == "add_medication":
            return self._add_medication(query)

        if intent == "log_medication_taken":
            return self._take_medication()

        if intent == "checkin":
            return self._checkin()

        if intent in ("insights", "report", "progress", "assessment"):
            return self._delegate(intent, query)

        # 5. Free text we could not classify - this is the only path where
        #    harmful content can actually reach us, so pay for the deep check.
        deep = safety.check(query, deep=True)
        if not deep["safe"]:
            log.warn("safety_block", reason=deep["reason"], matched=deep["matched"])
            return AgentReply(agent=self.name, text=deep["message"],
                              data={"blocked": True, "reason": deep["reason"]})

        return self._delegate(self._route(low), query)

    # --- logging --------------------------------------------------------

    def _do_log(self, intent: str, parsed: dict) -> AgentReply:
        agent, writer, key, template = LOG_ACTIONS[intent]
        value = parsed["entities"].get(key)
        try:
            if writer is not None:
                writer(value)
            elif intent == "log_steps":
                db.add_activity("steps", steps=value)
            elif intent == "log_exercise":
                db.add_activity("exercise", minutes=value)
            else:  # vitals share one writer keyed by metric name
                db.add_vital(key, value)
        except ValidationError as exc:
            return AgentReply(agent=self.name, text=exc.user_message,
                              data={"rejected": True, "field": exc.field})

        return AgentReply(agent=self.name, text=template.format(v=value),
                          data={"logged": True, "agent": agent, key: value})

    def _log_bp(self, parsed: dict) -> AgentReply:
        e = parsed["entities"]
        try:
            db.add_vital("systolic", e["systolic"], secondary=e["diastolic"])
        except ValidationError as exc:
            return AgentReply(agent=self.name, text=exc.user_message,
                              data={"rejected": True})
        return AgentReply(
            agent=self.name,
            text=f"Logged blood pressure {e['systolic']:g}/{e['diastolic']:g}.",
            data={"logged": True, "agent": "vitals"},
        )

    def _log_meal(self, parsed: dict) -> AgentReply:
        e = parsed["entities"]
        item = e.get("item") or "meal"
        try:
            db.add_meal(item, e.get("calories"))
        except ValidationError as exc:
            return AgentReply(agent=self.name, text=exc.user_message,
                              data={"rejected": True})
        return AgentReply(
            agent=self.name,
            text=f"Logged {item} at {e['calories']:g} calories.",
            data={"logged": True, "agent": "nutrition"},
        )

    def _add_medication(self, query: str) -> AgentReply:
        import re
        cleaned = re.sub(
            r"i take|i'm on|im on|add medication|remind me to take|prescribed",
            "", query, flags=re.IGNORECASE).strip(" .,")
        if not cleaned:
            return AgentReply(agent=self.name,
                              text="What's the medication called?")
        db.add_medication(cleaned[:80])
        return AgentReply(
            agent=self.name,
            text=(f"Added {cleaned[:80]} to your list. I'll track whether you've "
                  f"taken it - but I can't advise on doses."),
            data={"logged": True, "agent": "medication"},
        )

    def _take_medication(self) -> AgentReply:
        meds = db.query("SELECT id, name FROM medications "
                        "WHERE user_id = ? AND active = 1",
                        (db.current_user(),))
        if not meds:
            return AgentReply(agent=self.name,
                              text="You haven't added any medications yet.")
        for m in meds:
            db.log_medication_taken(m["id"])
        names = ", ".join(m["name"] for m in meds)
        return AgentReply(agent=self.name, text=f"Marked {names} as taken today.",
                          data={"logged": True, "agent": "medication"})

    # --- delegation -----------------------------------------------------

    def _delegate(self, target: str, query: str) -> AgentReply:
        specialist = self.bus.get(target) if self.bus else None
        if specialist is None:
            return AgentReply(
                agent=self.name,
                text="I can help with sleep, water, meals, activity, mood, "
                     "vitals or how you're feeling. Which one?",
            )
        self.bus.handoff(self.name, target, reason=f"user asked: {query}")
        return specialist.safe_handle(query)

    def _route(self, low: str) -> str:
        """
        Pick the specialist. The model decides when it is available,
        because a keyword table only knows the words somebody thought to
        write down: "I keep getting acidity after meals" is a symptom, and
        the word "meals" sent it to the nutrition agent.

        Keyword scoring remains as the offline fallback.
        """
        if llm.available():
            choice = llm.chat(
                system=ROUTER_PROMPT,
                user=low,
            ).strip().lower()
            if choice in ROUTES:
                log.info("llm_routed", target=choice)
                return choice

        # Offline. A complaint outranks everything else: "acidity after
        # meals" contains the word "meals" and is not about food.
        if any(shape.search(low) for shape in COMPLAINT_SHAPES):
            return "symptom"

        # A message naming actual foods is a meal, whatever surrounds it.
        from app.core import foods
        if foods.find(low):
            return "nutrition"

        scores = {
            agent: sum(len(kw) for kw in words if kw in low)
            for agent, words in ROUTES.items()
        }
        best = max(scores, key=scores.get)
        if scores[best] > 0:
            return best

        if llm.available():
            answer = llm.chat(
                system="Reply with exactly one word naming the best agent: "
                       "hydration, sleep, nutrition, activity, vitals, mood, "
                       "medication, or symptom.",
                user=low,
            ).lower().strip()
            if answer in ROUTES:
                log.info("llm_routed", target=answer)
                return answer

        return "symptom"

    def _checkin(self) -> AgentReply:
        """Ask every data-holding agent for its own summary line."""
        skip = {"coach", "insights", "report", "symptom"}
        reports = self.bus.broadcast(self.name, reason="daily check-in",
                                     exclude=tuple(skip))
        lines = []
        for agent in reports:
            peer = self.bus.get(agent)
            if peer:
                lines.append(peer.safe_handle("summary").text)
        return AgentReply(
            agent=self.name,
            text="\n".join(lines) or "Nothing logged yet today.",
            data={"reports": reports},
        )

    def report(self) -> dict:
        return {"role": "orchestrator"}
