"""
Model-driven meal resolution.

An earlier version of this used hand-written lists: these words are vague,
these meals usually come with a drink. That approach only ever knows what
somebody thought to write down. It handled "a burger" and fell straight
through on "a thali" or "shakshuka".

So the model runs the conversation instead. It is given the exchange so
far and decides for itself whether it can estimate the meal honestly, or
whether one more question would materially change the answer.

Two things are NOT delegated to the model:
  - calorie figures for foods we hold locally, which are grounded against
    app/core/foods.py rather than guessed
  - the decision to write anything, which stays with the agent

When Azure is unavailable the caller falls back to the local path, so the
app still logs meals offline, just without the conversation.
"""
import json

from app.core import foods
from app.core import logging as log
from app.services import llm

SYSTEM = """You log meals for a wellness app. You will be given the food \
part of a conversation, oldest first.

Decide whether you can estimate the total calories honestly.

Ask a question ONLY when the answer would change the estimate by roughly a \
third or more. A burger could be 330 or 690 kcal, so ask. A banana is a \
banana, so do not ask. Never ask about something the user already told you. \
Ask at most one short, natural question at a time, and never more than two \
questions in a whole conversation.

Reply with JSON only, no other text:
{"items":[{"name":"<food>","quantity":<number>,"kcal":<integer per unit>}],
 "done":<true|false>,
 "question":"<your question, or empty when done>"}

items must list everything eaten across the whole conversation, not just \
the latest message. kcal is per single unit, before multiplying by \
quantity. When done is true, question must be empty."""


def resolve(turns: list[str]) -> dict | None:
    """
    Work out the meal from the conversation so far.

    Returns {items, done, question} or None when the model is unavailable
    or returned something unusable, which tells the caller to fall back.
    """
    if not llm.available() or not turns:
        return None

    known = _reference(turns)
    user = "\n".join(f"- {t}" for t in turns)
    if known:
        user += ("\n\nReference calories for items we hold (per single "
                 "unit), use these exact numbers where they apply:\n" + known)

    raw = llm.chat(SYSTEM, user, temperature=0)
    if not raw:
        return None

    parsed = _parse(raw)
    if parsed is None:
        log.warn("food_ai_unparsable", raw=raw[:120])
        return None

    # Ground every figure we actually hold, so the model cannot drift on
    # foods we already know the answer for.
    for item in parsed["items"]:
        reference = foods.FOODS.get(item["name"].lower().strip())
        if reference:
            item["kcal_each"] = reference[0]
        else:
            item["kcal_each"] = item.get("kcal") or 0
        item["quantity"] = max(0.25, min(20, float(item.get("quantity") or 1)))
        item["kcal"] = int(round(item["kcal_each"] * item["quantity"]))
        item.setdefault("portion", "1 serving")

    parsed["items"] = [i for i in parsed["items"] if 0 < i["kcal"] <= 6000]
    log.info("food_ai", items=len(parsed["items"]), done=parsed["done"])
    return parsed


def _reference(turns: list[str]) -> str:
    """Calorie figures we hold for anything mentioned, to anchor the model."""
    found = foods.find(" ".join(turns))
    lines = {f"{f['name']}: {f['kcal_each']} kcal per {f['portion']}"
             for f in found}
    return "\n".join(sorted(lines))


def _parse(raw: str) -> dict | None:
    """Pull the JSON object out of a reply, tolerating code fences."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except (ValueError, TypeError):
        return None

    items = data.get("items")
    if not isinstance(items, list):
        return None

    clean = []
    for item in items:
        if isinstance(item, dict) and item.get("name"):
            clean.append({
                "name": str(item["name"])[:60],
                "quantity": item.get("quantity", 1),
                "kcal": item.get("kcal"),
            })

    return {
        "items": clean,
        "done": bool(data.get("done")),
        "question": str(data.get("question") or "")[:240],
    }
