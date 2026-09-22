"""Streaks, goals, achievements and the history series behind the charts."""
from app.store import db


def test_empty_state_has_no_streak_and_no_badges(bus):
    p = bus.get("progress").report()
    assert p["streak"] == 0
    assert p["days_logged"] == 0
    assert p["unlocked"] == []
    assert p["has_data"] is False


def test_logging_today_starts_a_streak(bus, clean_db):
    db.add_water(2)
    p = bus.get("progress").report()
    assert p["streak"] == 1
    assert any(a["key"] == "first_step" for a in p["unlocked"])


def test_streak_counts_consecutive_days(bus, clean_db):
    for i in range(4):
        db.add_water(3, day=db.days_ago(i))
    p = bus.get("progress").report()
    assert p["streak"] == 4
    assert any(a["key"] == "streak_3" for a in p["unlocked"])


def test_streak_survives_a_day_that_has_not_ended(bus, clean_db):
    """Nothing logged today yet should not break yesterday's streak."""
    for i in range(1, 4):
        db.add_water(3, day=db.days_ago(i))
    assert bus.get("progress").report()["streak"] == 3


def test_a_gap_breaks_the_streak(bus, clean_db):
    db.add_water(3, day=db.days_ago(0))
    db.add_water(3, day=db.days_ago(3))
    p = bus.get("progress").report()
    assert p["streak"] == 1
    assert p["days_logged"] == 2


def test_longest_streak_is_remembered_after_a_break(bus, clean_db):
    for i in range(10, 5, -1):              # five in a row, then a gap
        db.add_water(3, day=db.days_ago(i))
    db.add_water(3, day=db.days_ago(0))
    p = bus.get("progress").report()
    assert p["longest_streak"] == 5
    assert p["streak"] == 1


def test_rings_close_when_targets_are_met(bus, clean_db):
    db.add_water(8)
    goals = {g["key"]: g for g in bus.get("progress").report()["goals"]}
    assert goals["water"]["done"] is True
    assert goals["water"]["percent"] == 100
    assert goals["steps"]["done"] is False


def test_ring_percent_never_exceeds_100(bus, clean_db):
    db.add_water(20)
    water = next(g for g in bus.get("progress").report()["goals"]
                 if g["key"] == "water")
    assert water["percent"] == 100


def test_every_achievement_states_how_to_earn_it(bus):
    p = bus.get("progress").report()
    for a in p["unlocked"] + p["locked"]:
        assert a["name"] and a["how"], f"{a['key']} is missing its description"


def test_points_and_level_rise_with_progress(bus, clean_db):
    before = bus.get("progress").report()
    db.add_water(8)
    after = bus.get("progress").report()
    assert after["points"] > before["points"]
    assert after["level"] >= 1


def test_progress_is_reachable_through_the_coach(bus, clean_db):
    db.add_water(2)
    reply = bus.get("coach").handle("what is my streak?")
    assert "streak" in reply.text.lower()


def test_progress_queries_peers_rather_than_tables(bus, clean_db):
    """It is a meta-agent: its numbers must come through the bus."""
    db.add_water(2)
    bus.reset_trace()
    bus.get("progress").report()
    contacted = {e["to"] for e in bus.trace}
    assert {"hydration", "sleep", "activity"}.issubset(contacted)


# --- history series --------------------------------------------------

def test_series_returns_one_point_per_day(clean_db):
    s = db.series("sleep", 7)
    assert len(s["points"]) == 7
    assert s["points"][-1]["day"] == db.today()


def test_series_preserves_gaps_as_none(clean_db):
    db.add_sleep(6, day=db.days_ago(0))
    db.add_sleep(7, day=db.days_ago(3))
    values = [p["value"] for p in db.series("sleep", 5)["points"]]
    assert values[-1] == 6
    assert None in values, "a day with no log must stay null, not become zero"


def test_series_rejects_an_unknown_metric(clean_db):
    import pytest
    with pytest.raises(ValueError):
        db.series("blood_type", 7)


def test_all_series_covers_every_chart(clean_db):
    data = db.all_series(7)
    assert {"sleep", "water", "calories", "steps", "active", "mood"} <= set(data)


# --- quick logging ---------------------------------------------------

def test_quicklog_writes_through_the_validated_path(client):
    assert client.post("/api/quicklog",
                       json={"action": "water", "value": 3}).json()["ok"] is True
    assert client.get("/api/dashboard").json()["hydration"]["glasses_today"] == 3


def test_quicklog_refuses_an_implausible_value(client):
    d = client.post("/api/quicklog", json={"action": "sleep", "value": 99}).json()
    assert d["ok"] is False
    assert "18" in d["message"]


def test_quicklog_rejects_an_unknown_action(client):
    assert client.post("/api/quicklog",
                       json={"action": "teleport", "value": 1}).status_code == 404


# --- installable app shell -------------------------------------------

def test_manifest_is_served_at_the_root(client):
    r = client.get("/manifest.webmanifest")
    assert r.status_code == 200
    assert r.json()["start_url"] == "/"


def test_service_worker_is_served_from_the_root(client):
    """Scope rule: a worker under /static could not control the app shell."""
    r = client.get("/sw.js")
    assert r.status_code == 200
    assert "text/javascript" in r.headers["content-type"]


def test_static_assets_are_served(client):
    for path in ["/static/app.css", "/static/app.js", "/static/icon.svg"]:
        assert client.get(path).status_code == 200, path


# --- the demo dataset -------------------------------------------------

def test_the_seed_covers_a_month(clean_db):
    from scripts.seed import DAYS, seed_demo_data
    seed_demo_data()
    assert DAYS == 30
    assert len(db.logged_days(days=60)) >= 25


def test_the_seed_leaves_gaps_for_the_charts(clean_db):
    """A day with no log must show as a gap, not a zero, so the seed
    deliberately skips a few days to give the charts something to draw."""
    from scripts.seed import seed_demo_data
    seed_demo_data()
    values = [p["value"] for p in db.series("sleep", 30)["points"]]
    assert None in values
    assert values.count(None) >= 2


def test_the_seed_is_reproducible(clean_db):
    """The same numbers have to appear in a recorded video every time."""
    from scripts.seed import seed_demo_data
    seed_demo_data()
    first = db.series("sleep", 30)["points"]
    seed_demo_data()
    assert db.series("sleep", 30)["points"] == first


def test_the_seed_produces_the_sleep_and_mood_correlation(bus, clean_db):
    """
    The headline insight of the whole project. If the seeded mood does not
    actually track the seeded sleep, the demo has nothing to show.
    """
    from scripts.seed import seed_demo_data
    seed_demo_data()
    fresh = __import__("app.main", fromlist=["build_bus"]).build_bus()
    patterns = fresh.get("insights").handle("patterns").data["patterns"]
    joined = " ".join(p["insight"] for p in patterns).lower()
    assert "mood" in joined and "sleep" in joined


def test_the_seed_fills_the_profile_so_the_review_works(clean_db):
    """Otherwise the Review page opens a conversation instead of a result."""
    from scripts.seed import seed_demo_data
    seed_demo_data()
    profile = db.get_profile()
    assert profile.get("age") and profile.get("activity_level")


def test_is_empty_detects_a_fresh_database(clean_db):
    from scripts.seed import is_empty, seed_demo_data
    assert is_empty() is True
    seed_demo_data()
    assert is_empty() is False


# --- the headline insight, and the day it disappeared ---------------------

def test_the_sleep_mood_link_does_not_depend_on_todays_date(clean_db,
                                                            monkeypatch):
    """
    It did, and it broke.

    The rule used to fire when the sleep agent said "poor" and the mood
    agent said "low". Those are two independent threshold crossings, not
    a correlation, and the mood one is an average of 4 or below. On
    23 September the seeded month averaged 4.1 and the headline finding
    of the whole project silently vanished. Which side of the line it
    landed on depended on where the weekends fell in the window.

    So the rule measures the link now, and this walks a fortnight of
    start dates to prove the answer does not move with the calendar.
    """
    import datetime
    import app.store.db as store
    import scripts.seed as seeder
    from app.main import build_bus
    from app.store import users

    real_date = datetime.date

    class Frozen(real_date):
        target = None

        @classmethod
        def today(cls):
            return cls.target

    monkeypatch.setattr(seeder, "date", Frozen)
    monkeypatch.setattr(store, "date", Frozen)

    missed = []
    for offset in range(14):
        Frozen.target = real_date(2026, 9, 23) + datetime.timedelta(days=offset)
        store.delete_everything()
        person = users.create(f"day{offset}@example.com", "Day", "a-password-x")
        store.CURRENT_USER.set(person["id"])
        seeder.seed_demo_data()

        patterns = build_bus().get("insights").handle("patterns").data["patterns"]
        joined = " ".join(p["insight"] for p in patterns).lower()
        if "mood" not in joined or "sleep" not in joined:
            missed.append(str(Frozen.target))

    assert not missed, ("The sleep and mood link went missing on: "
                        + ", ".join(missed))


def test_the_link_is_measured_not_asserted(seeded_bus):
    """The evidence has to carry the number, or it is just a claim."""
    patterns = seeded_bus.get("insights").handle("patterns").data["patterns"]
    link = next(p for p in patterns if "tracking alongside" in p["insight"])
    assert "r=" in link["evidence"]
    assert "days they move together" in link["evidence"]
    assert link["agents"] == ["sleep", "mood"]


def test_a_week_is_not_enough_to_claim_a_link():
    """
    Over seven days the seeded series correlate at -0.55, the opposite of
    the real relationship. Claiming a trend from that would be worse than
    claiming nothing.
    """
    from app.agents.insights import MIN_PAIRED_DAYS, correlate
    assert MIN_PAIRED_DAYS >= 14
    week = {f"2026-09-{d:02d}": d for d in range(1, 8)}
    assert correlate(week, week) is None, "seven days should not qualify"


def test_a_flat_series_reports_no_link():
    """Dividing by a zero spread would invent a correlation."""
    from app.agents.insights import correlate
    days = {f"2026-09-{d:02d}": 7 for d in range(1, 21)}
    varies = {f"2026-09-{d:02d}": d for d in range(1, 21)}
    assert correlate(days, varies) is None
    assert correlate(days, days) is None


def test_correlate_finds_a_real_relationship():
    from app.agents.insights import correlate
    rising = {f"2026-09-{d:02d}": d for d in range(1, 21)}
    falling = {f"2026-09-{d:02d}": 21 - d for d in range(1, 21)}
    assert correlate(rising, rising)["r"] == 1.0
    assert correlate(rising, falling)["r"] == -1.0
    assert correlate(rising, rising)["days"] == 20


def test_correlate_only_uses_days_both_agents_have():
    from app.agents.insights import correlate
    a = {f"2026-09-{d:02d}": d for d in range(1, 26)}
    b = {f"2026-09-{d:02d}": d for d in range(1, 16)}
    assert correlate(a, b)["days"] == 15
    assert correlate(a, None) is None
    assert correlate({}, b) is None
