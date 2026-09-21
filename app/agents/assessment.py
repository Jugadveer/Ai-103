"""
Assessment agent - the whole-picture review.

This is the closest thing here to sitting down with someone and going
through the numbers. It asks every other agent what it holds, works out
roughly what the person needs in a day, compares that with what they
actually logged, and says what stands out.

Three things it deliberately does not do, because a student project has
no business doing them: it does not name a disease, it does not
recommend or adjust medication, and it does not tell anyone to change a
clinical treatment. Those requests are refused by the safety layer before
they ever arrive here. What it produces are observations about logged
data, each with the arithmetic behind it, and a clear statement of where
a clinician should take over.

It also asks first. A maintenance figure without an age is a guess, so
rather than assuming, it opens a short conversation to fill the gaps.
"""
from app.agents.base import BaseAgent, AgentReply
from app.core import dialog, energy
from app.core import logging as log
from app.core.errors import ValidationError
from app.core.validation import check_number
from app.store import db


# Asked in this order, one at a time. Each entry is the profile key, the
# question, and how to read the answer.
PROFILE_QUESTIONS = [
    ("age", "How old are you? I need it to estimate your energy needs."),
    ("sex", "And is the standard male or female equation the right one for "
            "you? The formula uses it, and you can say skip."),
    ("activity_level",
     "Roughly how active is a normal week for you: sedentary, light, "
     "moderate, active, or very active?"),
]


class AssessmentAgent(BaseAgent):
    name = "assessment"
    description = (
        "Reviews every agent's data together: estimates daily energy needs, "
        "checks logged intake against them, and flags what stands out. "
        "Never diagnoses and never advises on medication."
    )
    holds_data = False

    # ---------------- entry ----------------

    def handle(self, query: str) -> AgentReply:
        # A question about the subject deserves an answer, not this
        # agent's analysis. "Why do streaks help with habits" is not a
        # request for the current streak.
        spoken = self.try_answer(query)
        if spoken:
            return AgentReply(agent=self.name, text=spoken,
                              data={"answered": True})

        missing = self._missing_profile()
        if missing:
            return self._ask_for(missing[0])
        return self._review()

    def continue_dialog(self, query: str, context: dict) -> AgentReply:
        """Answering one of the profile questions."""
        key = context.get("asking")

        if dialog.is_cancel(query):
            self._close()
            return AgentReply(agent=self.name,
                              text="No problem, we can do this another time.")

        if key and not dialog.is_negative(query):
            stored = self._store(key, query)
            if stored is False:
                return AgentReply(
                    agent=self.name,
                    text=self._retry_wording(key),
                    data={"awaiting": True})

        # Either stored, or they declined to say. Move on either way.
        answered = set(context.get("answered", [])) | {key}
        remaining = [k for k in self._missing_profile() if k not in answered]
        if remaining:
            return self._ask_for(remaining[0], answered)

        self._close()
        return self._review()

    # ---------------- the review ----------------

    def _review(self) -> AgentReply:
        peers = self.bus.broadcast(self.name, reason="whole-picture review") if self.bus else {}
        profile = db.get_profile()
        vitals = peers.get("vitals", {})
        food = peers.get("nutrition", {})

        findings, needs = [], None
        weight = vitals.get("weight_kg")
        height = vitals.get("height_cm")
        age = self._as_number(profile.get("age"))

        if weight and height and age:
            needs = energy.maintenance(
                weight, height, int(age), profile.get("sex", ""),
                profile.get("activity_level", energy.DEFAULT_LEVEL))
            findings += self._energy_findings(needs, food, peers, profile)
        else:
            findings.append({
                "topic": "Energy needs",
                "text": "I cannot estimate your maintenance calories without "
                        "your height, weight and age. Add them on the Body "
                        "page and ask me again.",
                "evidence": "missing: " + ", ".join(
                    n for n, v in [("height", height), ("weight", weight),
                                   ("age", age)] if not v),
            })

        findings += self._other_findings(peers)

        log.info("assessment", findings=len(findings),
                 maintenance=needs["maintenance"] if needs else None)
        return AgentReply(
            agent=self.name,
            text=self._compose(findings, needs),
            data={"findings": findings, "energy": needs, "peers": peers},
        )

    def _energy_findings(self, needs: dict, food: dict, peers: dict,
                         profile: dict) -> list:
        """Intake against requirement, and whether the intake is believable."""
        out = [{
            "topic": "Maintenance estimate",
            "text": f"Your daily maintenance looks like roughly "
                    f"{needs['maintenance']} kcal, somewhere in the "
                    f"{needs['range_low']} to {needs['range_high']} range.",
            "evidence": f"Mifflin-St Jeor resting rate {needs['resting']} kcal, "
                        f"x{needs['activity_factor']} for "
                        f"{needs['activity_label'].lower()}",
        }]

        intake = food.get("calories_today", 0)
        meals = food.get("meals_today", 0)
        state = energy.balance(intake, needs["maintenance"])

        # Cross-check before interpreting. An intake far below requirement
        # is much more often incomplete logging than a real fast, and
        # saying "you are starving" to someone who just forgot lunch would
        # be both wrong and alarming.
        if state["verdict"] == "under_logged":
            out.append({
                "topic": "Intake looks incomplete",
                "text": f"You have {intake} kcal logged against a need of "
                        f"about {needs['maintenance']}. That is low enough "
                        f"that I think the day is part-logged rather than "
                        f"genuinely that small. Add what you have missed and "
                        f"ask me again.",
                "evidence": f"{meals} {'meal' if meals == 1 else 'meals'} "
                            f"logged, {state['percent']}% below maintenance",
            })
        elif state["verdict"] == "around":
            out.append({
                "topic": "Energy balance",
                "text": f"Today's {intake} kcal sits close to maintenance. "
                        f"On these numbers your weight would hold steady.",
                "evidence": f"{intake} against {needs['maintenance']} kcal, "
                            f"within {state['percent']}%",
            })
        else:
            direction = energy.VERDICT_WORDS[state["verdict"]]
            drift = abs(state["gap"]) * 7 / 7700     # 7700 kcal to a kg
            out.append({
                "topic": "Energy balance",
                "text": f"Today's {intake} kcal is {direction}, by about "
                        f"{abs(state['gap'])} kcal. Held for a week that is "
                        f"roughly {drift:.1f} kg of change, though one day "
                        f"tells you very little on its own.",
                "evidence": f"{intake} against {needs['maintenance']} kcal, "
                            f"{state['percent']}% {'below' if state['gap'] < 0 else 'above'}",
            })

        # Activity was assumed from what they told us, not measured, and
        # that assumption moves the whole figure. Say so.
        # The case that matters most is claiming an active week and logging
        # nothing: the multiplier then inflates the whole estimate. An
        # earlier version required logged activity to exist before checking,
        # which skipped exactly that case.
        move = peers.get("activity", {})
        claimed = profile.get("activity_level", energy.DEFAULT_LEVEL)
        barely_moved = (not move.get("has_data")
                        or move.get("status") == "sedentary")
        if claimed != "sedentary" and barely_moved:
            out.append({
                "topic": "Check the activity setting",
                "text": f"Your activity level is set to "
                        f"{claimed.replace('_', ' ')}, but very little "
                        f"movement is logged this week. If that is accurate, "
                        f"the maintenance figure above is probably too high.",
                "evidence": f"{move.get('minutes_week', 0)} active minutes "
                            f"logged, level set to {claimed}",
            })
        return out

    def _other_findings(self, peers: dict) -> list:
        """Observations from the rest of the picture, each with its evidence."""
        out = []
        sleep = peers.get("sleep", {})
        if sleep.get("has_data") and sleep.get("debt_hours", 0) >= 7:
            out.append({
                "topic": "Sleep",
                "text": "You are carrying more than a full night of sleep "
                        "debt, which affects appetite and energy as much as "
                        "it affects how tired you feel.",
                "evidence": f"{sleep['debt_hours']}h short over "
                            f"{sleep['nights_logged']} nights",
            })

        water = peers.get("hydration", {})
        if water.get("has_data") and water.get("status") == "low":
            out.append({
                "topic": "Fluids",
                "text": "Fluid intake is running below target, which is worth "
                        "fixing before reading much into the other numbers.",
                "evidence": f"{water.get('glasses_today')} of "
                            f"{water.get('target')} glasses today",
            })

        mood = peers.get("mood", {})
        if mood.get("has_data") and mood.get("status") == "low":
            out.append({
                "topic": "Mood",
                "text": "Your self-reported mood has been low. If that holds "
                        "for more than two weeks it is worth talking to a "
                        "doctor or counsellor, and I am not a substitute for "
                        "either.",
                "evidence": f"{mood.get('avg_score')}/10 average over "
                            f"{mood.get('days_logged')} days",
            })

        vitals = peers.get("vitals", {})
        for flag in vitals.get("flags", []):
            out.append({
                "topic": "A reading to raise with a doctor",
                "text": flag + " I cannot interpret it, and it should be "
                               "looked at by a clinician rather than acted on "
                               "from here.",
                "evidence": "self-reported reading",
            })

        meds = peers.get("medication", {})
        if meds.get("status") == "missed":
            out.append({
                "topic": "Medication",
                "text": f"Still to take today: {', '.join(meds['pending'])}. "
                        f"I track whether you have taken it and nothing else.",
                "evidence": f"{meds.get('adherence_week_pct')}% adherence "
                            f"this week",
            })
        return out

    def _compose(self, findings: list, needs: dict | None) -> str:
        lines = ["Here is the whole picture, and the working behind it.", ""]
        for i, f in enumerate(findings, 1):
            lines.append(f"{i}. {f['topic']}. {f['text']}")
            lines.append(f"   ({f['evidence']})")
        lines += [
            "",
            "These are observations about what you logged, not a diagnosis. "
            "Energy figures are estimates from a standard equation and are "
            "routinely out by ten percent. Anything medical belongs with a "
            "doctor, and the Report page will put all of this on one page "
            "for you to take to one.",
        ]
        return "\n".join(lines)

    # ---------------- the conversation ----------------

    def _missing_profile(self) -> list[str]:
        have = db.get_profile()
        return [k for k, _ in PROFILE_QUESTIONS if not have.get(k)]

    def _ask_for(self, key: str, answered: set | None = None) -> AgentReply:
        question = dict(PROFILE_QUESTIONS)[key]
        if self.bus:
            self.bus.ask_followup(self.name, "profile", question,
                                  {"asking": key,
                                   "answered": list(answered or [])})
        return AgentReply(agent=self.name, text=question,
                          data={"awaiting": True, "asking": key})

    def _store(self, key: str, answer: str) -> bool:
        low = (answer or "").strip().lower()

        if key == "age":
            digits = "".join(c for c in low if c.isdigit())
            if not digits:
                return False
            try:
                db.set_profile("age", int(check_number("age", int(digits))))
                return True
            except ValidationError:
                return False

        if key == "sex":
            if low.startswith(("m", "male")):
                db.set_profile("sex", "male")
            elif low.startswith(("f", "female", "w")):
                db.set_profile("sex", "female")
            else:
                db.set_profile("sex", "unstated")
            return True

        if key == "activity_level":
            for level in energy.ACTIVITY_LEVELS:
                if level.split("_")[0] in low:
                    db.set_profile("activity_level", level)
                    return True
            return False

        return False

    def _retry_wording(self, key: str) -> str:
        return {
            "age": "I need a number for that, in years.",
            "activity_level": "Pick one of sedentary, light, moderate, "
                              "active or very active.",
        }.get(key, "Sorry, I did not follow that one.")

    def _close(self) -> None:
        if self.bus:
            self.bus.clear_followup()

    def _as_number(self, value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    # ---------------- reporting ----------------

    def report(self) -> dict:
        profile = db.get_profile()
        return {
            "role": "review",
            "holds_data": False,
            "profile_complete": not self._missing_profile(),
            "age": profile.get("age"),
            "activity_level": profile.get("activity_level"),
        }
