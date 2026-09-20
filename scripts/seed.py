"""
Loads a realistic demo dataset.

Used by `python -m scripts.seed`, by POST /api/seed, and by the tests that
need a populated database. Keeping it in one place means the demo, the
tests and the video all show the same numbers.
"""
from app.store import db


def seed_demo_data() -> None:
    """A believable week for a sleep-deprived student."""
    db.init_db()
    db.clear_all()

    # Seven nights of short sleep -> a visible sleep debt.
    for i, hours in enumerate([5.0, 5.5, 6.0, 4.5, 5.2, 6.1, 5.4]):
        db.add_sleep(hours, quality="restless", day=db.days_ago(6 - i))

    # Today: under-hydrated and under-fed.
    db.add_water(2)
    db.add_meal("breakfast toast", 300)

    # Barely any movement this week.
    db.add_activity("walk", minutes=15, day=db.days_ago(4))
    db.add_activity("walk", minutes=20, day=db.days_ago(1))
    db.add_activity("steps", steps=2400)

    # Mood drifting down alongside the sleep debt.
    for i, score in enumerate([6, 5, 5, 4, 3, 3, 2]):
        db.add_mood(score, day=db.days_ago(6 - i))

    # A couple of vitals readings.
    db.add_vital("height_cm", 175)
    db.add_vital("weight_kg", 71.5)
    db.add_vital("heart_rate", 86)

    # One tracked medication, not yet taken today.
    db.add_medication("Vitamin D", schedule="daily")


if __name__ == "__main__":
    from app import config
    seed_demo_data()
    print(f"Demo data loaded into {config.DB_PATH}")
