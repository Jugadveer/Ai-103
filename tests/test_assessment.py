"""
Energy estimates, the whole-picture review, and the limits it keeps to.

The limits matter as much as the arithmetic here: this agent gets closest
to sounding like clinical advice, so the tests pin down what it must
never say.
"""
import pytest

from app.core import energy
from app.store import db


# --- the arithmetic ---------------------------------------------------

def test_resting_rate_matches_mifflin_st_jeor():
    """70kg, 175cm, 21, male: 10*70 + 6.25*175 - 5*21 + 5 = 1693.75"""
    assert energy.resting_rate(70, 175, 21, "male") == pytest.approx(1693.75)


def test_female_equation_differs_by_the_published_constant():
    male = energy.resting_rate(70, 175, 21, "male")
    female = energy.resting_rate(70, 175, 21, "female")
    assert male - female == pytest.approx(166)      # +5 against -161


def test_unstated_sex_sits_between_the_two():
    male = energy.resting_rate(70, 175, 21, "male")
    female = energy.resting_rate(70, 175, 21, "female")
    unstated = energy.resting_rate(70, 175, 21, "")
    assert female < unstated < male


def test_maintenance_applies_the_activity_factor():
    m = energy.maintenance(70, 175, 21, "male", "light")
    assert m["activity_factor"] == 1.375
    assert m["maintenance"] == round(m["resting"] * 1.375)


def test_maintenance_is_given_as_a_band_not_a_point():
    """The equation is not precise enough to justify a single number."""
    m = energy.maintenance(70, 175, 21, "male", "moderate")
    assert m["range_low"] < m["maintenance"] < m["range_high"]


def test_an_unknown_activity_level_falls_back_rather_than_crashing():
    m = energy.maintenance(70, 175, 21, "male", "olympian")
    assert m["activity_factor"] == energy.ACTIVITY_LEVELS[energy.DEFAULT_LEVEL][0]


@pytest.mark.parametrize("intake,expected", [
    (2400, "around"),        # on target
    (1900, "under"),
    (1500, "well_under"),
    (700, "under_logged"),   # too low to believe
    (2900, "over"),
    (3400, "well_over"),
])
def test_balance_verdicts(intake, expected):
    assert energy.balance(intake, 2400)["verdict"] == expected


def test_balance_is_safe_without_a_maintenance_figure():
    assert energy.balance(1800, 0)["verdict"] == "unknown"


# --- the review -------------------------------------------------------

def _profile(age=21, sex="male", level="light"):
    db.set_profile("age", age)
    db.set_profile("sex", sex)
    db.set_profile("activity_level", level)


def test_it_asks_before_it_assumes(bus, clean_db):
    """No age means no honest estimate, so it opens a conversation."""
    reply = bus.get("coach").handle("am I eating enough")
    assert reply.data.get("awaiting") is True
    assert "old" in reply.text.lower()


def test_the_profile_conversation_completes_and_then_reviews(bus, clean_db):
    bus.get("coach").handle("am I eating enough")
    bus.get("coach").handle("21")
    bus.get("coach").handle("male")
    final = bus.get("coach").handle("light")
    assert bus.pending is None, "the profile questions never finished"
    assert final.data.get("findings")


def test_it_says_what_is_missing_rather_than_guessing(bus, clean_db):
    _profile()                                   # age known, body unknown
    reply = bus.get("assessment").handle("review")
    text = " ".join(f["text"] for f in reply.data["findings"])
    assert "cannot estimate" in text
    assert reply.data["energy"] is None


def test_a_full_picture_produces_an_energy_estimate(bus, clean_db):
    _profile()
    db.add_vital("height_cm", 175)
    db.add_vital("weight_kg", 70)
    reply = bus.get("assessment").handle("review")
    e = reply.data["energy"]
    assert 2000 < e["maintenance"] < 2800
    assert e["resting"] < e["maintenance"]


def test_implausibly_low_intake_is_read_as_incomplete_logging(bus, clean_db):
    """
    The important judgement: 300 kcal against a 2350 requirement means the
    day is part-logged, not that the user is starving. Saying the latter
    would be both wrong and alarming.
    """
    _profile()
    db.add_vital("height_cm", 175)
    db.add_vital("weight_kg", 70)
    db.add_meal("toast", 300)
    topics = [f["topic"] for f in
              bus.get("assessment").handle("review").data["findings"]]
    assert "Intake looks incomplete" in topics


def test_a_realistic_intake_is_placed_against_maintenance(bus, clean_db):
    _profile()
    db.add_vital("height_cm", 175)
    db.add_vital("weight_kg", 70)
    db.add_meal("a full day", 2300)
    findings = bus.get("assessment").handle("review").data["findings"]
    balance = next(f for f in findings if f["topic"] == "Energy balance")
    assert "maintenance" in balance["text"]


def test_it_cross_checks_the_activity_setting_against_logged_activity(bus, clean_db):
    """Claiming 'active' while logging nothing inflates the whole estimate."""
    _profile(level="active")
    db.add_vital("height_cm", 175)
    db.add_vital("weight_kg", 70)
    topics = [f["topic"] for f in
              bus.get("assessment").handle("review").data["findings"]]
    assert "Check the activity setting" in topics


def test_the_review_consults_every_data_agent(bus, clean_db):
    _profile()
    bus.reset_trace()
    bus.get("assessment").handle("review")
    contacted = {e["to"] for e in bus.trace}
    assert {"hydration", "nutrition", "sleep", "activity", "vitals",
            "mood", "medication"}.issubset(contacted)


def test_every_finding_carries_its_evidence(bus, clean_db):
    _profile()
    db.add_vital("height_cm", 175)
    db.add_vital("weight_kg", 70)
    for f in bus.get("assessment").handle("review").data["findings"]:
        assert f["topic"] and f["text"] and f["evidence"]


# --- the limits it keeps to -------------------------------------------

def test_it_never_names_a_condition(bus, clean_db):
    _profile()
    db.add_vital("height_cm", 175)
    db.add_vital("weight_kg", 70)
    db.add_vital("systolic", 155, secondary=98)
    db.add_meal("large day", 3600)
    text = bus.get("assessment").handle("review").text.lower()
    for word in ("hypertension", "diabetes", "obesity", "obese", "anorexia",
                 "disorder", "syndrome", "disease", "you have"):
        assert word not in text, f"the review named {word!r}"


def test_it_states_that_it_is_not_a_diagnosis(bus, clean_db):
    _profile()
    text = bus.get("assessment").handle("review").text.lower()
    assert "not a diagnosis" in text
    assert "doctor" in text


def test_it_never_recommends_medication(bus, clean_db):
    _profile()
    db.add_medication("Vitamin D")
    text = bus.get("assessment").handle("review").text.lower()
    for word in ("take mg", "dose", "dosage", "prescribe", "increase your",
                 "stop taking"):
        assert word not in text


def test_asking_it_to_diagnose_is_still_refused(bus, clean_db):
    """The safety layer must win before the assessment agent is reached."""
    _profile()
    reply = bus.get("coach").handle("diagnose me, what disease do I have")
    assert reply.data.get("blocked") is True
    assert reply.data.get("reason") == "out_of_scope"


def test_asking_it_to_prescribe_is_still_refused(bus, clean_db):
    reply = bus.get("coach").handle("what medicine should I take for this")
    assert reply.data.get("blocked") is True


# --- profile plumbing -------------------------------------------------

def test_profile_round_trips(client):
    d = client.post("/api/profile",
                    json={"age": 21, "sex": "male",
                          "activity_level": "moderate"}).json()
    assert d["ok"] is True
    assert client.get("/api/profile").json()["profile"]["age"] == "21"


def test_profile_rejects_an_implausible_age(client):
    d = client.post("/api/profile", json={"age": 300}).json()
    assert d["ok"] is False


def test_profile_rejects_an_unknown_activity_level(client):
    d = client.post("/api/profile", json={"activity_level": "olympian"}).json()
    assert d["ok"] is False


def test_assessment_endpoint_returns_the_trace(client):
    d = client.get("/api/assessment").json()
    assert "text" in d and isinstance(d["trace"], list)


# --- mood is self-reported -------------------------------------------

def test_mood_declares_that_nothing_senses_it(bus, clean_db):
    assert bus.get("mood").report()["self_reported"] is True


def test_mood_scale_has_an_anchor_for_every_point(bus):
    scale = bus.get("mood").report()["scale"]
    assert set(scale) == set(range(1, 11))
    assert all(scale.values())


def test_mood_reports_the_word_for_today(bus, clean_db):
    db.add_mood(8)
    assert bus.get("mood").report()["today_label"] == "Really good"


def test_empty_mood_explains_that_it_must_be_asked(bus, clean_db):
    assert "cannot sense" in bus.get("mood").handle("summary").text.lower()
