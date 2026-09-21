"""
Nutrition agent - meals and calories.

Unlike the other specialists, this one holds a conversation. "I ate a
burger" is not enough to log honestly: the answer is somewhere between
330 and 690 calories depending on which burger, and whether there were
fries and a drink alongside.

Whether to ask, and what to ask, is decided by the model in
app/services/food_ai.py. There is deliberately no list of vague foods
here: any such list only knows what somebody thought to write down, and
falls over on the first unfamiliar dish.

What the model does NOT decide: calorie figures for foods we hold are
grounded against app/core/foods.py, and nothing reaches the database
except through the validated writer below.

Three ways in, all ending in the same place:
  text   "I had a big mac and a medium coke"
  voice  the same, transcribed
  photo  read by Azure OpenAI vision, confirmed before logging
"""
import re

from app.agents.base import BaseAgent, AgentReply
from app.core import dialog, foods
from app.core import logging as log
from app.core.errors import ValidationError
from app.services import food_ai
from app.store import db

TARGET_CALORIES = 2000
MAX_TURNS = 4            # no meal is worth more questions than this
SIDES_THRESHOLD = 200    # below this it is a snack, not a meal with sides


class NutritionAgent(BaseAgent):
    name = "nutrition"
    description = (
        "Tracks meals and calories. Asks a follow-up when a meal is too "
        "vague to log honestly, and reads food photos."
    )

    EXPLICIT_KCAL = re.compile(r"(\d{2,4})\s*(?:kcal|calories|cals|cal)\b")

    # ---------------- entry ----------------

    def handle(self, query: str) -> AgentReply:
        # A stated number is not a guess, so it needs no conversation.
        stated = self.EXPLICIT_KCAL.search((query or "").lower())
        if stated:
            named = foods.find(query)
            return self._commit([{
                "name": named[0]["name"] if named else self._label(query),
                "quantity": 1, "kcal_each": int(stated.group(1)),
                "kcal": int(stated.group(1)),
            }])

        if self._is_summary_request(query):
            return self._summary()

        # "how much protein do I need" is a question, not a meal. Without
        # this it was parsed as food, logged nothing, and read as the app
        # ignoring what was asked.
        spoken = self.try_answer(query)
        if spoken:
            return AgentReply(agent=self.name, text=spoken,
                              data={**self.report(), "answered": True})

        # Anything else routed here is treated as a meal. If the model finds
        # no food in it, nothing is logged and it says so.
        return self._resolve([query])

    def continue_dialog(self, query: str, context: dict) -> AgentReply:
        """The user answered. Hand the whole exchange back to the model."""
        if dialog.is_cancel(query):
            self._close()
            return AgentReply(agent=self.name,
                              text="Dropped it, nothing logged.")

        # A photo proposal is a yes or no, not another round of resolution.
        if context.get("from_photo"):
            return self._photo_answer(query, context)

        # An open question must not swallow a change of subject. Answering
        # "what did you eat?" with "my knee hurts when I run" is not an
        # answer, and treating it as one made the app look deaf.
        if self._changes_the_subject(query):
            self._close()
            return None

        turns = list(context.get("turns", [])) + [query]

        # A closing phrase stops the questions. It can still name a final
        # item ("a coke, that's all"), so keep the words minus the phrase.
        if dialog.is_negative(query):
            remainder = dialog.strip_closing(query)
            final = turns[:-1] + ([remainder] if remainder else [])
            return self._resolve(final, force_done=True)

        if len(turns) > MAX_TURNS:
            return self._resolve(turns, force_done=True)

        return self._resolve(turns)

    # ---------------- resolution ----------------

    def _resolve(self, turns: list[str], force_done: bool = False) -> AgentReply:
        asked_before = bool(self.bus and self.bus.pending
                            and self.bus.pending.context.get("asked_sides"))
        outcome = food_ai.resolve(turns)

        if outcome is None:
            # Offline, or the model returned nothing usable.
            return self._offline(turns)

        items = outcome["items"]
        finished = force_done or outcome["done"] or not outcome["question"]

        # One generic accompaniment question before the first commit. This
        # is a rule rather than a model judgement because it has to be
        # reliable: a main logged without its drink is routinely out by a
        # few hundred calories, and the model is inconsistent about asking.
        # It is food-agnostic, asked at most once, and skipped the moment
        # the user says they are done.
        # A snack does not need a drink question. Size, not food identity,
        # decides - still no list of specific foods.
        substantial = sum(i["kcal"] for i in items) >= SIDES_THRESHOLD
        if (finished and not force_done and substantial and not asked_before):
            question = "Anything to drink or any sides with that?"
            running = sum(i["kcal"] for i in items)
            if self.bus:
                self.bus.ask_followup(
                    self.name, "food",
                    f"{foods.describe(items)}, {running} kcal so far. {question}",
                    {"turns": turns, "asked_sides": True})
            return AgentReply(
                agent=self.name,
                text=f"{foods.describe(items)}, {running} kcal so far. {question}",
                data={"awaiting": True, "running_total": running,
                      "items": items})

        if finished:
            return self._commit(items)

        question = outcome["question"]
        running = sum(i["kcal"] for i in items)
        if items:
            question = (f"{foods.describe(items)}, {running} kcal so far. "
                        f"{question}")

        if self.bus:
            self.bus.ask_followup(self.name, "food", question, {"turns": turns})
        return AgentReply(agent=self.name, text=question,
                          data={"awaiting": True, "running_total": running,
                                "items": items})

    def _offline(self, turns: list[str]) -> AgentReply:
        """
        No model available. Log what the local table recognises rather than
        asking questions we would have no way to follow up on.
        """
        items = foods.find(" ".join(turns))
        if not items:
            return AgentReply(
                agent=self.name,
                text="I could not place that food, and I am offline so I "
                     "cannot look it up. Tell me roughly how many calories "
                     "it was and I will log it.",
                data={"awaiting": True})
        return self._commit(items, offline=True)

    def _commit(self, items: list[dict], offline: bool = False) -> AgentReply:
        self._close()
        if not items:
            return AgentReply(agent=self.name,
                              text="Nothing logged. Tell me what you ate "
                                   "whenever you like.")
        total = sum(i["kcal"] for i in items)
        try:
            for item in items:
                label = (f"{item['quantity']:g} x {item['name']}"
                         if item.get("quantity", 1) != 1 else item["name"])
                db.add_meal(label, max(1, item["kcal"]))
        except ValidationError as exc:
            return AgentReply(agent=self.name, text=exc.user_message,
                              data={"rejected": True})

        log.info("meal_logged", items=len(items), kcal=total, offline=offline)
        day = self.report()
        note = (" Recognised offline from typical serving sizes."
                if offline else " These are estimates from typical servings.")
        return AgentReply(
            agent=self.name,
            text=(f"Logged {foods.describe(items)}. That is {total} kcal, "
                  f"putting you at {day['calories_today']} for the day.{note}"),
            data={"logged": True, "items": items, "kcal": total,
                  "estimated": True})

    def _changes_the_subject(self, query: str) -> bool:
        """
        True when a reply cannot plausibly be answering a food question.

        Judged by what is absent rather than by a list of other topics:
        no recognisable food, no number, and none of the words that close
        or confirm an exchange.
        """
        if foods.find(query):
            return False
        if re.search(r"\d", query or ""):
            return False
        if (dialog.is_negative(query) or dialog.is_affirmative(query)
                or dialog.is_cancel(query)):
            return False
        return len((query or "").split()) >= 3

    def _close(self) -> None:
        if self.bus:
            self.bus.clear_followup()

    # ---------------- photo ----------------

    def safe_handle_photo(self, description: str) -> AgentReply:
        try:
            return self.propose_from_photo(description)
        except Exception as exc:
            log.error("photo_log_failed", error=str(exc)[:160])
            return AgentReply(agent=self.name,
                              text="I had trouble reading that photo.",
                              data={"error": True})

    def propose_from_photo(self, description: str) -> AgentReply:
        """
        Vision can be confidently wrong: in testing, a plain red square came
        back as "a sandwich and soup". So a photo proposes, and the user
        confirms before anything is written.
        """
        outcome = food_ai.resolve([f"From a photo: {description}"])
        items = outcome["items"] if outcome else foods.find(description)
        if not items:
            return AgentReply(
                agent=self.name,
                text="I could not work out the food in that photo. Tell me "
                     "what it was instead.",
                data={"awaiting": True})

        total = sum(i["kcal"] for i in items)
        question = (f"From the photo that looks like {foods.describe(items)}, "
                    f"about {total} kcal. Shall I log it? Say yes, or tell me "
                    f"what it actually was.")
        if self.bus:
            self.bus.ask_followup(self.name, "photo", question,
                                  {"items": items, "from_photo": True})
        return AgentReply(agent=self.name, text=question,
                          data={"awaiting": True, "proposed": items,
                                "kcal": total, "from_photo": True})

    def _photo_answer(self, query: str, context: dict) -> AgentReply:
        if dialog.is_affirmative(query):
            return self._commit(context.get("items", []))
        if dialog.is_negative(query):
            self._close()
            return AgentReply(agent=self.name,
                              text="Nothing logged. Tell me what it was.",
                              data={"awaiting": True})
        return self._resolve([query])          # a correction

    # ---------------- helpers ----------------

    SUMMARY_PHRASES = (
        "summary", "how many calories", "how much have i", "what have i",
        "calories today", "calorie total", "how am i doing", "my intake",
    )

    def _is_summary_request(self, text: str) -> bool:
        low = (text or "").lower().strip()
        if not low:
            return True
        return any(p in low for p in self.SUMMARY_PHRASES)

    def _label(self, text: str) -> str:
        cleaned = re.sub(
            r"\d+|kcal|calories|cals|cal\b|i ate|i had|about|roughly|around",
            " ", (text or "").lower())
        return re.sub(r"\s+", " ", cleaned).strip(" ,.-")[:60] or "meal"

    # ---------------- reporting ----------------

    def _summary(self) -> AgentReply:
        f = self.report()
        text = ("Nothing logged today yet. Tell me what you ate, or send a "
                "photo of it." if f["meals_today"] == 0 else
                f"You have logged {f['meals_today']} "
                f"{'meal' if f['meals_today'] == 1 else 'meals'} today, "
                f"about {f['calories_today']} calories.")
        return AgentReply(agent=self.name, text=text, data=f)

    def report(self) -> dict:
        rows = db.query(
            "SELECT COUNT(*) AS n, COALESCE(SUM(calories), 0) AS cals "
            "FROM meals WHERE user_id = ? AND day = ?",
            (db.current_user(), db.today()))
        n = rows[0]["n"] if rows else 0
        cals = rows[0]["cals"] if rows else 0
        return {
            "has_data": n > 0,
            "meals_today": n,
            "calories_today": cals,
            "target": TARGET_CALORIES,
            "status": "low" if cals < TARGET_CALORIES * 0.5 else "ok",
        }
