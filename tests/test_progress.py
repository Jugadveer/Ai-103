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
