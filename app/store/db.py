"""
SQLite storage. Plain sqlite3 on purpose - no ORM, easy to explain.

One table per domain, one agent per table. Agents never read each other's
tables; they ask each other through the bus.
"""
import sqlite3
from datetime import date, datetime, timedelta

from app import config
from app.core import logging as log
from app.core.validation import check_number, check_text

SCHEMA = """
CREATE TABLE IF NOT EXISTS meals (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    day       TEXT NOT NULL,
    item      TEXT NOT NULL,
    calories  INTEGER NOT NULL,
    logged_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS water (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    day       TEXT NOT NULL,
    glasses   INTEGER NOT NULL,
    logged_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sleep (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    day       TEXT NOT NULL,
    hours     REAL NOT NULL,
    quality   TEXT,
    logged_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS symptoms (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    day       TEXT NOT NULL,
    note      TEXT NOT NULL,
    logged_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS activity (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    day       TEXT NOT NULL,
    kind      TEXT NOT NULL,
    minutes   INTEGER NOT NULL DEFAULT 0,
    steps     INTEGER NOT NULL DEFAULT 0,
    logged_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vitals (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    day       TEXT NOT NULL,
    metric    TEXT NOT NULL,
    value     REAL NOT NULL,
    secondary REAL,
    logged_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mood (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    day       TEXT NOT NULL,
    score     INTEGER NOT NULL,
    note      TEXT,
    logged_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS medications (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL,
    schedule  TEXT NOT NULL,
    active    INTEGER NOT NULL DEFAULT 1,
    added_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS med_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    day       TEXT NOT NULL,
    med_id    INTEGER NOT NULL,
    taken     INTEGER NOT NULL DEFAULT 1,
    logged_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_meals_day    ON meals(day);
CREATE INDEX IF NOT EXISTS idx_water_day    ON water(day);
CREATE INDEX IF NOT EXISTS idx_sleep_day    ON sleep(day);
CREATE INDEX IF NOT EXISTS idx_activity_day ON activity(day);
CREATE INDEX IF NOT EXISTS idx_vitals_day   ON vitals(day);
CREATE INDEX IF NOT EXISTS idx_mood_day     ON mood(day);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
    log.info("db_ready", path=config.DB_PATH)


def today() -> str:
    return date.today().isoformat()


def days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def query(sql: str, params: tuple = ()) -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _insert(sql: str, params: tuple) -> int:
    with connect() as conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid or 0


# --- writers. Each one validates before it touches the database. ---------

def add_meal(item: str, calories, day: str | None = None) -> None:
    cals = check_number("calories", calories)
    name = check_text("meal name", item, max_len=120)
    _insert(
        "INSERT INTO meals (day, item, calories, logged_at) VALUES (?, ?, ?, ?)",
        (day or today(), name, int(cals), _now()),
    )


def add_water(glasses, day: str | None = None) -> None:
    n = check_number("water_glasses", glasses)
    _insert(
        "INSERT INTO water (day, glasses, logged_at) VALUES (?, ?, ?)",
        (day or today(), int(n), _now()),
    )


def add_sleep(hours, quality: str = "", day: str | None = None) -> None:
    h = check_number("sleep_hours", hours)
    _insert(
        "INSERT INTO sleep (day, hours, quality, logged_at) VALUES (?, ?, ?, ?)",
        (day or today(), h, quality, _now()),
    )


def add_symptom(note: str, day: str | None = None) -> None:
    text = check_text("symptom", note)
    _insert(
        "INSERT INTO symptoms (day, note, logged_at) VALUES (?, ?, ?)",
        (day or today(), text, _now()),
    )


def add_activity(kind: str, minutes=0, steps=0, day: str | None = None) -> None:
    mins = int(check_number("exercise_mins", minutes)) if minutes else 0
    step_count = int(check_number("steps", steps)) if steps else 0
    _insert(
        "INSERT INTO activity (day, kind, minutes, steps, logged_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (day or today(), kind or "activity", mins, step_count, _now()),
    )


def add_vital(metric: str, value, secondary=None, day: str | None = None) -> None:
    val = check_number(metric, value)
    sec = check_number("diastolic", secondary) if secondary is not None else None
    _insert(
        "INSERT INTO vitals (day, metric, value, secondary, logged_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (day or today(), metric, val, sec, _now()),
    )


def add_mood(score, note: str = "", day: str | None = None) -> None:
    s = check_number("mood_score", score)
    _insert(
        "INSERT INTO mood (day, score, note, logged_at) VALUES (?, ?, ?, ?)",
        (day or today(), int(s), note, _now()),
    )


def add_medication(name: str, schedule: str = "daily") -> int:
    med = check_text("medication name", name, max_len=80)
    return _insert(
        "INSERT INTO medications (name, schedule, active, added_at) "
        "VALUES (?, ?, 1, ?)",
        (med, schedule, _now()),
    )


def log_medication_taken(med_id: int, day: str | None = None) -> None:
    _insert(
        "INSERT INTO med_log (day, med_id, taken, logged_at) VALUES (?, ?, 1, ?)",
        (day or today(), med_id, _now()),
    )


def clear_all() -> None:
    """Wipe every table. Used by tests and the demo seeder."""
    tables = ("meals", "water", "sleep", "symptoms", "activity",
              "vitals", "mood", "medications", "med_log")
    with connect() as conn:
        for t in tables:
            conn.execute(f"DELETE FROM {t}")
