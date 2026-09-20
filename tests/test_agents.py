"""Each agent in isolation: does report() return sane facts?"""
import pytest

from app.store import db

DATA_AGENTS = ["hydration", "nutrition", "sleep", "activity",
               "vitals", "mood", "medication", "symptom"]


def test_all_agents_register(bus):
    assert len(bus.agents) == 13
    for name in ["coach"] + DATA_AGENTS + ["progress", "assessment", "insights", "report"]:
        assert name in bus.agents, f"{name} did not register"


@pytest.mark.parametrize("name", DATA_AGENTS)
def test_every_agent_reports_without_data(bus, name):
    """An empty database must not crash any agent."""
    assert isinstance(bus.get(name).report(), dict)


@pytest.mark.parametrize("name", DATA_AGENTS)
def test_every_agent_answers_without_data(bus, name):
    reply = bus.get(name).handle("summary")
    assert reply.text and isinstance(reply.text, str)


def test_hydration_counts_and_flags_shortfall(bus, clean_db):
    db.add_water(2)
    r = bus.get("hydration").report()
    assert r["glasses_today"] == 2
    assert r["shortfall"] == 6
    assert r["status"] == "low"


def test_hydration_ok_when_target_met(bus, clean_db):
    db.add_water(8)
    assert bus.get("hydration").report()["status"] == "ok"


def test_sleep_computes_average_and_debt(bus, clean_db):
    for i, h in enumerate([5.0, 5.0, 5.0]):
        db.add_sleep(h, day=db.days_ago(i))
    r = bus.get("sleep").report()
    assert r["nights_logged"] == 3
    assert r["avg_hours"] == 5.0
    assert r["debt_hours"] == 9.0      # 3 nights x 3h short
    assert r["status"] == "poor"


def test_nutrition_totals_calories(bus, clean_db):
    db.add_meal("toast", 300)
    db.add_meal("rice", 500)
    r = bus.get("nutrition").report()
    assert r["meals_today"] == 2
    assert r["calories_today"] == 800


def test_activity_tracks_steps_and_minutes(bus, clean_db):
    db.add_activity("walk", minutes=30)
    db.add_activity("steps", steps=6000)
    r = bus.get("activity").report()
    assert r["steps_today"] == 6000
    assert r["minutes_today"] == 30


def test_activity_flags_sedentary_week(bus, clean_db):
    assert bus.get("activity").report()["status"] == "sedentary"


def test_vitals_computes_bmi(bus, clean_db):
    db.add_vital("height_cm", 175)
    db.add_vital("weight_kg", 70)
    r = bus.get("vitals").report()
    assert r["bmi"] == 22.9
    assert r["bmi_band"] == "in the healthy range"


def test_vitals_flags_high_blood_pressure(bus, clean_db):
    db.add_vital("systolic", 150, secondary=95)
    r = bus.get("vitals").report()
    assert r["status"] == "attention"
    assert r["flags"]


def test_vitals_does_not_flag_normal_readings(bus, clean_db):
    db.add_vital("systolic", 118, secondary=76)
    db.add_vital("heart_rate", 68)
    assert bus.get("vitals").report()["status"] == "ok"


def test_mood_average_and_falling_trend(bus, clean_db):
    for i, score in enumerate([8, 7, 4, 3]):      # oldest first
        db.add_mood(score, day=db.days_ago(3 - i))
    r = bus.get("mood").report()
    assert r["days_logged"] == 4
    assert r["trend"] == "falling"


def test_mood_flags_persistent_low(bus, clean_db):
    for i in range(5):
        db.add_mood(3, day=db.days_ago(i))
    assert bus.get("mood").report()["status"] == "low"


def test_medication_tracks_pending(bus, clean_db):
    med_id = db.add_medication("Vitamin D")
    r = bus.get("medication").report()
    assert r["tracked"] == 1
    assert r["pending"] == ["Vitamin D"]
    assert r["status"] == "missed"

    db.log_medication_taken(med_id)
    r2 = bus.get("medication").report()
    assert r2["pending"] == []
    assert r2["status"] == "ok"


def test_agent_failure_is_isolated(bus):
    """One broken agent must not break the response."""
    broken = bus.get("sleep")
    broken.report = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    assert broken.safe_report()["status"] == "unavailable"

    broken.handle = lambda q: (_ for _ in ()).throw(RuntimeError("boom"))
    reply = broken.safe_handle("anything")
    assert reply.data.get("error") is True
    assert reply.text
