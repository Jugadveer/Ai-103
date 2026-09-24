"""
Figures that get restated, and figures that accumulate.

Most of what this app records piles up through the day: another glass of
water, another meal, another walk. Two of them do not. You sleep once a
night, and a step count read off a phone is already the total for the
day - saying either one again corrects the figure rather than adding to
it.

Both were wrong. Logging seven hours twice put fourteen hours in the
sleep chart and flipped the status from "poor" to "ok", which quietly
removed the app's main finding about the demo record. The tests below
pin the replacing behaviour, and just as importantly pin that the
accumulating things still accumulate.
"""
import pytest

from app.core import nlu
from app.core.validation import ValidationError
from app.store import db


# --- the two that replace -------------------------------------------------

def test_sleeping_is_restated_not_added(clean_db):
    db.add_sleep(7)
    db.add_sleep(6)
    assert db.query("SELECT SUM(hours) h FROM sleep WHERE user_id = ?",
                    (db.current_user(),))[0]["h"] == 6


def test_the_sleep_agent_sees_one_night(bus):
    db.add_sleep(4.8)
    db.add_sleep(6)
    report = bus.get("sleep").report()
    assert report["last_night"] == 6
    assert report["nights_logged"] == 1


def test_a_second_sleep_figure_does_not_rescue_a_poor_average(seeded_bus):
    """
    The failure that started this. The seeded record shows 4.8 hours last
    night against a 5.6 average, which is what every demo question hangs
    off. Adding a six on top used to read as 10.8 hours and status 'ok'.
    """
    db.add_sleep(6)
    report = seeded_bus.get("sleep").report()
    assert report["last_night"] == 6
    assert report["status"] == "poor"


def test_steps_are_restated_not_added(clean_db):
    db.set_steps(6000)
    db.set_steps(10000)
    assert db.query("SELECT SUM(steps) s FROM activity WHERE user_id = ?",
                    (db.current_user(),))[0]["s"] == 10000


def test_restating_steps_leaves_exercise_minutes_alone(clean_db):
    """Only the rows set_steps wrote are cleared."""
    db.add_activity("walk", minutes=30)
    db.set_steps(6000)
    db.set_steps(10000)
    rows = db.query("SELECT SUM(steps) s, SUM(minutes) m FROM activity "
                    "WHERE user_id = ?", (db.current_user(),))[0]
    assert rows["s"] == 10000
    assert rows["m"] == 30


def test_yesterdays_figures_are_untouched(clean_db):
    db.add_sleep(8, day=db.days_ago(1))
    db.set_steps(9000, day=db.days_ago(1))
    db.add_sleep(5)
    db.set_steps(3000)
    sleep = {r["day"]: r["h"] for r in db.query(
        "SELECT day, SUM(hours) h FROM sleep WHERE user_id = ? GROUP BY day",
        (db.current_user(),))}
    assert sleep[db.days_ago(1)] == 8
    assert sleep[db.today()] == 5


def test_a_rejected_value_does_not_erase_what_was_there(clean_db):
    """Validation runs before the delete, so a typo cannot wipe the day."""
    db.add_sleep(7)
    with pytest.raises(ValidationError):
        db.add_sleep(400)
    assert db.query("SELECT SUM(hours) h FROM sleep WHERE user_id = ?",
                    (db.current_user(),))[0]["h"] == 7


def test_replacing_stays_inside_one_account(clean_db):
    """The delete is owner-scoped like every other statement."""
    from app.store import users
    other = users.create(email="other@example.com", name="Other",
                         password="another-password")
    db.add_sleep(8)
    db.set_steps(12000)

    mine = db.current_user()

    db.CURRENT_USER.set(other["id"])
    db.add_sleep(5)
    db.set_steps(2000)

    assert db.query("SELECT SUM(hours) h FROM sleep WHERE user_id = ?",
                    (other["id"],))[0]["h"] == 5
    assert db.query("SELECT SUM(hours) h FROM sleep WHERE user_id = ?",
                    (mine,))[0]["h"] == 8


# --- the ones that must keep accumulating ---------------------------------

@pytest.mark.parametrize("writer,column,table,first,second,total", [
    (db.add_water, "glasses", "water", 2, 3, 5),
    (db.add_mood, "score", "mood", 4, 6, 10),
])
def test_things_that_pile_up_still_pile_up(clean_db, writer, column,
                                           table, first, second, total):
    writer(first)
    writer(second)
    got = db.query(f"SELECT SUM({column}) v FROM {table} WHERE user_id = ?",
                   (db.current_user(),))[0]["v"]
    assert got == total


def test_meals_still_accumulate(clean_db):
    db.add_meal("toast", 200)
    db.add_meal("curry", 600)
    assert db.query("SELECT SUM(calories) c FROM meals WHERE user_id = ?",
                    (db.current_user(),))[0]["c"] == 800


def test_exercise_minutes_still_accumulate(clean_db):
    db.add_activity("walk", minutes=20)
    db.add_activity("gym", minutes=30)
    assert db.query("SELECT SUM(minutes) m FROM activity WHERE user_id = ?",
                    (db.current_user(),))[0]["m"] == 50


# --- saying the number out loud -------------------------------------------

@pytest.mark.parametrize("said", [
    "I walked 10k steps",
    "i walked 10000 steps",
    "10k steps",
    "10,000 steps",
    "walked 10K steps today",
    "ten k steps",
    "I did 10000 steps today",
])
def test_every_way_people_say_ten_thousand_steps(said):
    parsed = nlu.parse(said)
    assert parsed["intent"] == "log_steps", said
    assert parsed["entities"]["steps"] == 10000, said


def test_a_shortened_count_is_not_read_as_exercise_minutes(clean_db):
    """
    "I walked 10k steps" used to log ten minutes of walking: no step rule
    matched '10k', so the exercise rule matched the bare 10 underneath it.
    """
    parsed = nlu.parse("I walked 10k steps")
    assert parsed["intent"] != "log_exercise"
    assert parsed["entities"].get("exercise_mins") is None


def test_a_thousands_separator_is_not_read_as_zero(clean_db):
    """'10,000 steps' matched the '000' and logged nothing at all."""
    assert nlu.parse("10,000 steps")["entities"]["steps"] == 10000


@pytest.mark.parametrize("said,intent", [
    ("I weigh 70 kg", "log_vital_weight"),
    ("I ate 500 kcal", "log_meal"),
    ("I walked 30 minutes", "log_exercise"),
    ("I slept 7 hours", "log_sleep"),
])
def test_a_lone_k_is_expanded_and_a_unit_is_not(said, intent):
    """kg, kcal and km keep their k. Only a k standing alone means 1000."""
    assert nlu.parse(said)["intent"] == intent, said


def test_asking_about_steps_still_logs_nothing():
    assert nlu.parse("how many steps did I take")["intent"] == "question"


# --- and the whole way through, as a person would do it -------------------

def test_saying_it_twice_through_the_coach_restates_it(bus):
    bus.get("coach").handle("I walked 6k steps")
    reply = bus.get("coach").handle("I walked 10k steps")
    assert "10,000" in reply.text
    assert bus.get("activity").report()["steps_today"] == 10000


def test_the_quick_entry_sets_rather_than_adds(client):
    client.post("/api/quicklog", json={"action": "steps", "value": 6000})
    client.post("/api/quicklog", json={"action": "steps", "value": 10000})
    assert client.get("/api/dashboard").json()["activity"]["steps_today"] == 10000


def test_an_implausible_step_count_is_still_refused(client):
    reply = client.post("/api/quicklog",
                        json={"action": "steps", "value": 500000})
    assert reply.json()["ok"] is False
