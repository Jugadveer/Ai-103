"""
Food recognition, multi-turn clarification, and self-reported vitals.

These run in MOCK_MODE, so the model is unavailable and the offline path
is what gets exercised. That is deliberate: the offline path is the one
that has to hold up if Azure is unreachable during the presentation.
"""
import pytest

from app.core import dialog, foods
from app.store import db


# --- food recognition -------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("a big mac", "big mac"),
    ("I had butter chicken", "butter chicken"),
    ("chicken biryani", "chicken biryani"),
    ("large fries", "large fries"),
])
def test_longest_name_wins(text, expected):
    """'butter chicken' must not be read as plain 'chicken'."""
    assert foods.find(text)[0]["name"] == expected


@pytest.mark.parametrize("text,name,qty", [
    ("two rotis and dal", "roti", 2),
    ("3 idli with sambar", "idli", 3),
    ("four chapatis", "chapati", 4),
    ("I had two dosas", "dosa", 2),
    ("a banana", "banana", 1),
])
def test_quantities_including_plurals(text, name, qty):
    """Regression: 'two rotis' matched nothing because of the plural s."""
    item = next(i for i in foods.find(text) if i["name"] == name)
    assert item["quantity"] == qty
    assert item["kcal"] == item["kcal_each"] * qty


def test_multiple_items_in_one_sentence():
    items = foods.find("a big mac with large fries and a coke")
    assert {i["name"] for i in items} == {"big mac", "large fries", "coke"}
    assert foods.total(items) == 563 + 480 + 140


def test_unknown_food_is_not_invented():
    assert foods.find("I ate a quesadilla") == []


def test_describe_reads_naturally():
    assert "2 x roti" in foods.describe(foods.find("two rotis"))


# --- closing phrases --------------------------------------------------

@pytest.mark.parametrize("text", [
    "no", "nothing else", "that's all", "thats all", "just that",
    "a medium coke, thats all", "one serving, nothing else",
])
def test_closing_phrases_end_the_exchange(text):
    assert dialog.is_negative(text) is True


@pytest.mark.parametrize("text", ["a big mac", "one serving", "a medium coke"])
def test_ordinary_answers_do_not_end_it(text):
    assert dialog.is_negative(text) is False


def test_closing_phrase_is_stripped_but_the_food_survives():
    """'a medium coke, that's all' still has to log the coke."""
    assert dialog.strip_closing("a medium coke, thats all") == "a medium coke"
    assert foods.find(dialog.strip_closing("a medium coke, thats all"))


def test_cancel_is_recognised():
    assert dialog.is_cancel("never mind") is True
    assert dialog.is_cancel("a big mac") is False


# --- the conversation -------------------------------------------------

def test_offline_logs_what_it_recognises(bus, clean_db):
    """With no model, it logs rather than asking questions it cannot follow."""
    reply = bus.get("coach").handle("I had a big mac and large fries")
    assert reply.data.get("logged") is True
    assert bus.get("nutrition").report()["calories_today"] == 563 + 480


def test_offline_says_so_when_the_food_is_unknown(bus, clean_db):
    reply = bus.get("coach").handle("I ate a quesadilla")
    assert reply.data.get("awaiting") is True
    assert "offline" in reply.text.lower()


def test_an_explicit_calorie_count_needs_no_conversation(bus, clean_db):
    reply = bus.get("coach").handle("I ate a wrap, 520 calories")
    assert reply.data.get("logged") is True
    assert bus.get("nutrition").report()["calories_today"] == 520


def test_a_pending_question_routes_the_next_message_back(bus, clean_db):
    """The heart of the clarification flow."""
    bus.ask_followup("nutrition", "food", "Which burger?", {"turns": ["a burger"]})
    assert bus.pending is not None
    bus.get("coach").handle("a big mac")
    assert bus.pending is None, "the pending question was never resolved"
    assert bus.get("nutrition").report()["meals_today"] >= 1


def test_cancelling_a_question_logs_nothing(bus, clean_db):
    bus.ask_followup("nutrition", "food", "Which burger?", {"turns": ["a burger"]})
    reply = bus.get("coach").handle("never mind")
    assert "nothing logged" in reply.text.lower()
    assert bus.get("nutrition").report()["meals_today"] == 0


def test_safety_still_runs_while_a_question_is_open(bus, clean_db):
    """A red flag must win even mid-conversation. This is the important one."""
    bus.ask_followup("nutrition", "food", "Which burger?", {"turns": ["a burger"]})
    reply = bus.get("coach").handle("I have crushing chest pain")
    assert reply.data.get("blocked") is True
    assert "112" in reply.text


def test_a_photo_proposes_rather_than_logs(bus, clean_db):
    """Vision can be confidently wrong, so nothing is written unprompted."""
    reply = bus.get("nutrition").propose_from_photo("1 cheeseburger, 1 fries")
    assert reply.data.get("awaiting") is True
    assert reply.data.get("from_photo") is True
    assert bus.get("nutrition").report()["meals_today"] == 0

    confirmed = bus.get("coach").handle("yes")
    assert confirmed.data.get("logged") is True
    assert bus.get("nutrition").report()["meals_today"] > 0


def test_declining_a_photo_logs_nothing(bus, clean_db):
    bus.get("nutrition").propose_from_photo("1 cheeseburger")
    reply = bus.get("coach").handle("no")
    assert bus.get("nutrition").report()["meals_today"] == 0
    assert "nothing logged" in reply.text.lower()


# --- vitals are self-reported ----------------------------------------

def test_vitals_declare_that_nothing_is_measured(bus):
    assert bus.get("vitals").report()["self_reported"] is True


def test_empty_vitals_explain_the_limitation(bus, clean_db):
    text = bus.get("vitals").handle("summary").text
    assert "cannot measure" in text.lower()


def test_bmi_is_computed_from_two_entered_numbers(client):
    d = client.post("/api/vitals", json={"height_cm": 175, "weight_kg": 70}).json()
    assert d["ok"] is True
    assert d["vitals"]["bmi"] == 22.9
    assert d["vitals"]["bmi_band"] == "in the healthy range"


def test_bmi_waits_for_the_missing_half(client):
    d = client.post("/api/vitals", json={"weight_kg": 70}).json()
    assert d["vitals"]["bmi"] is None
    assert d["vitals"]["missing_for_bmi"] == "height"


def test_vitals_endpoint_refuses_an_implausible_reading(client):
    d = client.post("/api/vitals", json={"weight_kg": 500}).json()
    assert d["ok"] is False
    assert "300" in d["errors"][0]


def test_raised_blood_pressure_is_flagged_not_diagnosed(client):
    d = client.post("/api/vitals",
                    json={"systolic": 150, "diastolic": 95}).json()
    v = d["vitals"]
    assert v["status"] == "attention"
    assert "above the usual reference range" in v["flags"][0]
    # flagged, never named as a condition
    assert "hypertension" not in " ".join(v["flags"]).lower()


def test_normal_readings_are_not_flagged(client):
    d = client.post("/api/vitals",
                    json={"systolic": 118, "diastolic": 76,
                          "heart_rate": 68}).json()
    assert d["vitals"]["status"] == "ok"
    assert d["vitals"]["flags"] == []


def test_photo_endpoint_rejects_a_non_image(client):
    d = client.post("/api/photo", json={"image": "x" * 40}).json()
    assert d["ok"] is False


def test_sleep_exposes_last_night_for_the_rings(bus, clean_db):
    db.add_sleep(9)
    assert bus.get("sleep").report()["last_night"] == 9
