"""
Loads a realistic month of demo data.

Used by `python -m scripts.seed`, by POST /api/seed, by the tests that
need a populated database, and by a new account that ticks "start with
sample data" on the way in. Keeping it in one place means the demo, the
tests, the video and the hosted app all show the same numbers.

The dataset is deliberately shaped rather than random:

  - sleep declines over the month, so the sleep-debt figure is real
  - mood declines alongside it, so the sleep/mood correlation the
    insights agent looks for is actually present and not contrived
  - three days are missing entirely, so the gaps in the trend charts
    have something to show
  - weekends are more active and better slept, as they usually are

A fixed random seed keeps it identical on every run, which matters when
the same numbers have to appear in a recorded video.
"""
import random
from datetime import date, timedelta

from app.store import db

DAYS = 30
SEED = 20260921        # fixed, so the demo is reproducible

# Days with nothing logged at all. Real logging has holes, and the charts
# draw a gap rather than a zero, which is worth being able to point at.
MISSED_DAYS = {17, 16, 8}

BREAKFASTS = [("toast", 80), ("poha", 210), ("oats", 160), ("idli", 60),
              ("omelette", 160), ("cereal", 200), ("dosa", 170)]
LUNCHES = [("dal", 150), ("rice", 200), ("chicken curry", 300),
           ("rajma", 210), ("chole", 250), ("paneer butter masala", 380),
           ("roti", 110), ("curd rice", 250)]
DINNERS = [("chapati", 110), ("dal makhani", 280), ("veg biryani", 430),
           ("palak paneer", 300), ("fried rice", 400), ("soup", 120),
           ("grilled sandwich", 350)]
SNACKS = [("banana", 105), ("samosa", 260), ("tea", 50), ("biscuit", 50),
          ("coffee", 60), ("gulab jamun", 150)]

SYMPTOM_NOTES = [
    (12, "headache in the afternoon again"),
    (9, "felt dizzy standing up this morning"),
    (5, "tired all day even after coffee"),
    (2, "headache after skipping lunch"),
]


def seed_demo_data(days: int = DAYS) -> None:
    """Wipe everything and write a shaped month of history."""
    rng = random.Random(SEED)
    db.init_db()
    db.clear_all()

    # Profile, so the Review page can estimate energy needs immediately
    # instead of opening a conversation the moment someone lands on it.
    db.set_profile("age", 21)
    db.set_profile("sex", "male")
    db.set_profile("activity_level", "light")

    med_id = db.add_medication("Vitamin D", schedule="daily")

    for offset in range(days - 1, -1, -1):
        if offset in MISSED_DAYS:
            continue

        day = db.days_ago(offset)
        weekend = date.fromisoformat(day).weekday() >= 5
        # 0.0 at the start of the month, 1.0 today: everything drifts.
        drift = 1 - (offset / max(1, days - 1))

        _seed_sleep(rng, day, offset, weekend, drift)
        _seed_water(rng, day, drift, offset)
        _seed_meals(rng, day, offset, drift)
        _seed_activity(rng, day, weekend, drift)
        _seed_mood(rng, day, weekend, drift)

        # Medication mostly taken, with a realistic few misses and none
        # yet today, so the "still to take" state is visible on arrival.
        if offset > 0 and rng.random() > 0.15:
            db.log_medication_taken(med_id, day=day)

    _seed_vitals(days)
    _seed_symptoms()


def _seed_sleep(rng, day, offset, weekend, drift):
    # Starts around 7.5 hours, ends around 5. The decline is the story.
    base = 7.4 - (2.4 * drift)
    if weekend:
        base += 0.9
    hours = round(max(3.5, min(9.5, rng.gauss(base, 0.45))), 1)
    quality = "restless" if hours < 6 else "ok"
    db.add_sleep(hours, quality=quality, day=day)


def _seed_water(rng, day, drift, offset=None):
    if offset == 0:
        db.add_water(2, day=day)      # today, so far
        return
    glasses = max(1, round(rng.gauss(7 - 3 * drift, 1.2)))
    db.add_water(min(12, glasses), day=day)


def _seed_meals(rng, day, offset, drift):
    item, kcal = rng.choice(BREAKFASTS)
    db.add_meal(item, kcal, day=day)

    # Lunch gets skipped more often as the month goes on, which is what
    # makes the "intake looks incomplete" finding fire on the worst days.
    if rng.random() > 0.15 + 0.3 * drift:
        for item, kcal in rng.sample(LUNCHES, 2):
            db.add_meal(item, kcal, day=day)

    # Today stays deliberately part-logged: it is early in the day.
    if offset > 0:
        for item, kcal in rng.sample(DINNERS, 2):
            db.add_meal(item, kcal, day=day)
        if rng.random() > 0.5:
            item, kcal = rng.choice(SNACKS)
            db.add_meal(item, kcal, day=day)


def _seed_activity(rng, day, weekend, drift):
    steps = int(max(400, rng.gauss(8200 - 4200 * drift, 1600)))
    db.set_steps(steps, day=day)

    chance = 0.62 if weekend else 0.42 - 0.2 * drift
    if rng.random() < chance:
        kind = rng.choice(["walk", "gym", "run", "cycling", "yoga"])
        db.add_activity(kind, minutes=rng.choice([20, 25, 30, 40, 45]),
                        day=day)


def _seed_mood(rng, day, weekend, drift):
    # Tracks sleep downward, which is the correlation the insights agent
    # is built to find. Present in the data, not asserted by the code.
    # Accelerating decline rather than linear: the recent fortnight has
    # to average at or below 4 for the agent to call it low, and a
    # straight line left it hovering just above.
    base = 7.6 - (5.2 * (drift ** 1.4))
    if weekend:
        base += 0.5
    db.add_mood(max(1, min(10, round(rng.gauss(base, 0.7)))), day=day)


def _seed_vitals(days):
    db.add_vital("height_cm", 175, day=db.days_ago(days - 1))
    for offset, weight in ((days - 1, 70.2), (21, 70.6), (14, 71.0),
                           (7, 71.3), (1, 71.5)):
        if offset < days:
            db.add_vital("weight_kg", weight, day=db.days_ago(offset))
    db.add_vital("heart_rate", 86, day=db.days_ago(3))
    db.add_vital("systolic", 128, secondary=84, day=db.days_ago(3))


def _seed_symptoms():
    for offset, note in SYMPTOM_NOTES:
        db.add_symptom(note, day=db.days_ago(offset))


def is_empty() -> bool:
    """True when nothing has ever been logged, in any domain."""
    return not db.logged_days(days=3650)


def seed_local_account(email: str = "demo@local", password: str = "demo1234",
                       name: str = "Demo") -> dict:
    """
    Make a local account and fill it with the demo month.

    Every row belongs to somebody now, so seeding with nobody signed in
    would write a month of history that no account can ever see. This
    gives the data an owner you can actually sign in as.
    """
    from app.core.errors import ValidationError
    from app.store import users

    db.init_db()
    try:
        user = users.create(email, name, password)
    except ValidationError:
        user = users.public(users.find_by_email(email))
    db.CURRENT_USER.set(user["id"])
    seed_demo_data()
    return user


if __name__ == "__main__":
    from app import config

    account = seed_local_account()
    where = config.DATABASE_URL and "Postgres" or config.DB_PATH
    print(f"Seeded {DAYS} days into {where}")
    print(f"Sign in as  {account['email']}  /  demo1234")
