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
