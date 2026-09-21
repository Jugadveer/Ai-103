"""
Storage. Plain SQL on purpose - no ORM, easy to read and to explain.

One table per domain, one agent per table. Agents never read each other's
tables; they ask each other through the bus.

Two backends. SQLite is the default and is what runs locally. If
DATABASE_URL is set the same SQL runs against Postgres instead, which is
what makes a hosted deployment keep your data: a serverless host throws
its filesystem away between requests, so a file-backed database there is
a promise the app cannot keep.

Every row belongs to a user. The owner is not passed around by hand; it
comes from CURRENT_USER, which the request layer sets once from the
session cookie. A query that forgets the filter would show one person
another person's health record, so tests/test_isolation.py reads every
SQL string in the codebase and fails if one touching a user table has no
user_id condition.
"""
import contextvars
import sqlite3
import threading
from datetime import date, datetime, timedelta

from app import config
from app.core import logging as log
from app.core.validation import check_number, check_text

# Set per request from the session cookie. 0 means nobody is signed in,
# which no user row ever uses, so an unauthenticated read returns nothing
# rather than everything.
CURRENT_USER: contextvars.ContextVar[int] = contextvars.ContextVar(
    "current_user_id", default=0)


def current_user() -> int:
    return CURRENT_USER.get()


# Tables holding personal data. Every one carries user_id.
OWNED_TABLES = ("meals", "water", "sleep", "symptoms", "activity",
                "vitals", "mood", "medications", "med_log", "profile")

# {id} differs between the two backends and nothing else does.
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            {id},
    email         TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meals (
    id        {id},
    user_id   INTEGER NOT NULL,
    day       TEXT NOT NULL,
    item      TEXT NOT NULL,
    calories  INTEGER NOT NULL,
    logged_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS water (
    id        {id},
    user_id   INTEGER NOT NULL,
    day       TEXT NOT NULL,
    glasses   INTEGER NOT NULL,
    logged_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sleep (
    id        {id},
    user_id   INTEGER NOT NULL,
    day       TEXT NOT NULL,
    hours     REAL NOT NULL,
    quality   TEXT,
    logged_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS symptoms (
    id        {id},
    user_id   INTEGER NOT NULL,
    day       TEXT NOT NULL,
    note      TEXT NOT NULL,
    logged_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS activity (
    id        {id},
    user_id   INTEGER NOT NULL,
    day       TEXT NOT NULL,
    kind      TEXT NOT NULL,
    minutes   INTEGER NOT NULL DEFAULT 0,
    steps     INTEGER NOT NULL DEFAULT 0,
    logged_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vitals (
    id        {id},
    user_id   INTEGER NOT NULL,
    day       TEXT NOT NULL,
    metric    TEXT NOT NULL,
    value     REAL NOT NULL,
    secondary REAL,
    logged_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mood (
    id        {id},
    user_id   INTEGER NOT NULL,
    day       TEXT NOT NULL,
    score     INTEGER NOT NULL,
    note      TEXT,
    logged_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS medications (
    id        {id},
    user_id   INTEGER NOT NULL,
    name      TEXT NOT NULL,
    schedule  TEXT NOT NULL,
    active    INTEGER NOT NULL DEFAULT 1,
    added_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS med_log (
    id        {id},
    user_id   INTEGER NOT NULL,
    day       TEXT NOT NULL,
    med_id    INTEGER NOT NULL,
    taken     INTEGER NOT NULL DEFAULT 1,
    logged_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS profile (
    id        {id},
    user_id   INTEGER NOT NULL,
    key       TEXT NOT NULL,
    value     TEXT NOT NULL,
    set_at    TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_profile_key ON profile(user_id, key);
CREATE INDEX IF NOT EXISTS idx_meals_day    ON meals(user_id, day);
CREATE INDEX IF NOT EXISTS idx_water_day    ON water(user_id, day);
CREATE INDEX IF NOT EXISTS idx_sleep_day    ON sleep(user_id, day);
CREATE INDEX IF NOT EXISTS idx_activity_day ON activity(user_id, day);
CREATE INDEX IF NOT EXISTS idx_vitals_day   ON vitals(user_id, day);
CREATE INDEX IF NOT EXISTS idx_mood_day     ON mood(user_id, day);
"""

POSTGRES = bool(config.DATABASE_URL)


# --- connections ---------------------------------------------------------
# SQLite connections are cheap, so one per call is fine. A Postgres
# connection costs a network round trip and a TLS handshake, and a single
# dashboard request runs about thirty queries, so those are pooled.

_pool = None
_pool_lock = threading.Lock()


def _postgres_pool():
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                from psycopg_pool import ConnectionPool
                from psycopg.rows import dict_row
                _pool = ConnectionPool(
                    config.DATABASE_URL, min_size=0, max_size=4,
                    # Few connections on purpose, and none while idle.
                    # A burstable Postgres allows about fifty in total,
                    # and on a serverless host every warm instance keeps
                    # its own pool, so these numbers multiply rather than
                    # share. min_size=0 means an instance nobody is using
                    # holds nothing; it costs one connection setup on the
                    # next request, which is cheaper than running out.
                    #
                    # check is the one that matters off a normal server. A
                    # serverless instance is frozen between requests and
                    # thawed later, by which time the other end may have
                    # dropped a connection this pool still believes in.
                    # Without this the symptom is a request that fails
                    # once, for no reason, and works on retry.
                    check=ConnectionPool.check_connection,
                    max_idle=120,      # let idle ones go rather than rot
                    # Ten seconds to get a connection, not the default
                    # thirty: a database that is genuinely down should say
                    # so while someone is still looking at the screen.
                    timeout=10,
                    kwargs={
                        "row_factory": dict_row,
                        # Hosted Postgres is usually reached through
                        # PgBouncer in transaction mode, where consecutive
                        # statements can land on different server
                        # connections. psycopg prepares a statement after
                        # it has run a few times, and the prepared version
                        # only exists on the connection that made it, so
                        # the pooler eventually routes a query to a
                        # connection that has never heard of it and the
                        # request dies with "prepared statement does not
                        # exist". It appears only after some traffic,
                        # which makes it look intermittent.
                        #
                        # Turning preparation off costs a little on
                        # repeated queries and makes the app work the same
                        # on every provider, pooled or direct.
                        "prepare_threshold": None,
                    },
                    open=True)
    return _pool


class _Session:
    """A connection borrowed for the length of one `with` block."""

    def __init__(self):
        self._ctx = None
        self.conn = None

    def __enter__(self):
        if POSTGRES:
            self._ctx = _postgres_pool().connection()
            self.conn = self._ctx.__enter__()
        else:
            self.conn = sqlite3.connect(config.DB_PATH)
            self.conn.row_factory = sqlite3.Row
        return self

    def __exit__(self, *exc):
        if POSTGRES:
            return self._ctx.__exit__(*exc)
        if exc[0] is None:
            self.conn.commit()
        self.conn.close()
        return False

    def run(self, sql: str, params: tuple = ()):
        return self.conn.execute(_placeholders(sql), params)


def _placeholders(sql: str) -> str:
    """SQL is written with ? throughout. Postgres wants %s."""
    return sql.replace("?", "%s") if POSTGRES else sql


def connect() -> _Session:
    return _Session()


def _retire_pre_accounts_file() -> None:
    """
    Move aside a database written before accounts existed.

    Every table gained a user_id when sign-in arrived. CREATE TABLE IF NOT
    EXISTS will not add a column to a table that is already there, so an
    older file would survive startup and then fail on the first query with
    "no such column: user_id".

    Such a file cannot contain anyone's real record, because there was no
    way to have an account when it was written; it is demo or development
    data. It is renamed rather than deleted, so if it mattered it is still
    on disk next to the new one.
    """
    import os
    if POSTGRES or not os.path.exists(config.DB_PATH):
        return
    with connect() as s:
        tables = {r["name"] for r in s.run(
            "SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
        if "meals" not in tables:
            return                                    # fresh or empty file
        columns = {r["name"] for r in
                   s.run("PRAGMA table_info(meals)").fetchall()}
        if "user_id" in columns:
            return                                    # already current
    retired = config.DB_PATH + ".pre-accounts"
    os.replace(config.DB_PATH, retired)
    log.info("retired_old_database", moved_to=retired,
             note="written before sign-in existed, so it holds no account data")


def init_db() -> None:
    _retire_pre_accounts_file()
    id_column = ("SERIAL PRIMARY KEY" if POSTGRES
                 else "INTEGER PRIMARY KEY AUTOINCREMENT")
    statements = [s.strip() for s in SCHEMA.format(id=id_column).split(";")
                  if s.strip()]
    with connect() as s:
        for statement in statements:
            s.run(statement)
    log.info("db_ready", backend="postgres" if POSTGRES else "sqlite")


def today() -> str:
    return date.today().isoformat()


def days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def query(sql: str, params: tuple = ()) -> list[dict]:
    with connect() as s:
        return [dict(r) for r in s.run(sql, params).fetchall()]


def _insert(sql: str, params: tuple) -> int:
    """Insert a row owned by the signed-in user and return its id."""
    params = (current_user(),) + params
    if POSTGRES:
        with connect() as s:
            row = s.run(sql + " RETURNING id", params).fetchone()
            return row["id"] if row else 0
    with connect() as s:
        return s.run(sql, params).lastrowid or 0


# --- writers. Each one validates before it touches the database. ---------
# The leading user_id column is filled in by _insert, so no caller can
# forget it and no caller can spoof it.

def add_meal(item: str, calories, day: str | None = None) -> None:
    cals = check_number("calories", calories)
    name = check_text("meal name", item, max_len=120)
    _insert(
        "INSERT INTO meals (user_id, day, item, calories, logged_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (day or today(), name, int(cals), _now()),
    )


def add_water(glasses, day: str | None = None) -> None:
    n = check_number("water_glasses", glasses)
    _insert(
        "INSERT INTO water (user_id, day, glasses, logged_at) "
        "VALUES (?, ?, ?, ?)",
        (day or today(), int(n), _now()),
    )


def add_sleep(hours, quality: str = "", day: str | None = None) -> None:
    h = check_number("sleep_hours", hours)
    _insert(
        "INSERT INTO sleep (user_id, day, hours, quality, logged_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (day or today(), h, quality, _now()),
    )


def add_symptom(note: str, day: str | None = None) -> None:
    text = check_text("symptom", note)
    _insert(
        "INSERT INTO symptoms (user_id, day, note, logged_at) "
        "VALUES (?, ?, ?, ?)",
        (day or today(), text, _now()),
    )


def add_activity(kind: str, minutes=0, steps=0, day: str | None = None) -> None:
    mins = int(check_number("exercise_mins", minutes)) if minutes else 0
    step_count = int(check_number("steps", steps)) if steps else 0
    _insert(
        "INSERT INTO activity (user_id, day, kind, minutes, steps, logged_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (day or today(), kind or "activity", mins, step_count, _now()),
    )


def add_vital(metric: str, value, secondary=None, day: str | None = None) -> None:
    val = check_number(metric, value)
    sec = check_number("diastolic", secondary) if secondary is not None else None
    _insert(
        "INSERT INTO vitals (user_id, day, metric, value, secondary, logged_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (day or today(), metric, val, sec, _now()),
    )


def add_mood(score, note: str = "", day: str | None = None) -> None:
    s = check_number("mood_score", score)
    _insert(
        "INSERT INTO mood (user_id, day, score, note, logged_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (day or today(), int(s), note, _now()),
    )


def add_medication(name: str, schedule: str = "daily") -> int:
    med = check_text("medication name", name, max_len=80)
    return _insert(
        "INSERT INTO medications (user_id, name, schedule, active, added_at) "
        "VALUES (?, ?, ?, 1, ?)",
        (med, schedule, _now()),
    )


def log_medication_taken(med_id: int, day: str | None = None) -> None:
    _insert(
        "INSERT INTO med_log (user_id, day, med_id, taken, logged_at) "
        "VALUES (?, ?, ?, 1, ?)",
        (day or today(), med_id, _now()),
    )


# --- profile -------------------------------------------------------------
# Age, sex and usual activity level. Needed to estimate energy needs, and
# nothing else. Sex is asked for because the standard equation uses it.

def set_profile(key: str, value) -> None:
    with connect() as s:
        s.run(
            "INSERT INTO profile (user_id, key, value, set_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT (user_id, key) DO UPDATE SET value = excluded.value, "
            "set_at = excluded.set_at",
            (current_user(), key, str(value), _now()))


def get_profile() -> dict:
    return {r["key"]: r["value"] for r in query(
        "SELECT key, value FROM profile WHERE user_id = ?", (current_user(),))}


def clear_all() -> None:
    """Wipe this user's rows. Used by tests and the demo seeder."""
    with connect() as s:
        for table in OWNED_TABLES:
            s.run(f"DELETE FROM {table} WHERE user_id = ?", (current_user(),))


def delete_everything() -> None:
    """Every row of every table, including accounts. Tests only."""
    with connect() as s:
        for table in OWNED_TABLES + ("users",):
            s.run(f"DELETE FROM {table}")


# --- history series, for charts -----------------------------------------
# One row per day with gaps preserved as None, so a chart can show a break
# in logging rather than drawing a misleading straight line across it.

SERIES = {
    "sleep":    ("SELECT day, SUM(hours)    v FROM sleep    WHERE user_id = ? AND day >= ? GROUP BY day", "h"),
    "water":    ("SELECT day, SUM(glasses)  v FROM water    WHERE user_id = ? AND day >= ? GROUP BY day", "glasses"),
    "calories": ("SELECT day, SUM(calories) v FROM meals    WHERE user_id = ? AND day >= ? GROUP BY day", "kcal"),
    "steps":    ("SELECT day, SUM(steps)    v FROM activity WHERE user_id = ? AND day >= ? GROUP BY day", "steps"),
    "active":   ("SELECT day, SUM(minutes)  v FROM activity WHERE user_id = ? AND day >= ? GROUP BY day", "min"),
    "mood":     ("SELECT day, AVG(score)    v FROM mood     WHERE user_id = ? AND day >= ? GROUP BY day", "/10"),
}


def series(metric: str, days: int = 14) -> dict:
    """Return {'metric','unit','points':[{'day','value'}]} with gaps as None."""
    if metric not in SERIES:
        raise ValueError(f"unknown metric {metric!r}")
    sql, unit = SERIES[metric]
    rows = {r["day"]: r["v"] for r in
            query(sql, (current_user(), days_ago(days - 1)))}

    points = []
    for offset in range(days - 1, -1, -1):
        day = days_ago(offset)
        value = rows.get(day)
        # Whole numbers stay whole: 2 glasses, not 2.0. Postgres returns
        # AVG as a Decimal, which is neither int nor float, so the test is
        # "is it already an integer" rather than "what type is it".
        if value is not None and not isinstance(value, int):
            value = round(float(value), 1)
        points.append({"day": day, "value": value})
    return {"metric": metric, "unit": unit, "points": points}


def all_series(days: int = 14) -> dict:
    return {name: series(name, days) for name in SERIES}


def logged_days(days: int = 60) -> set[str]:
    """Every day on which the user logged anything at all."""
    tables = ("meals", "water", "sleep", "activity", "vitals", "mood", "med_log")
    found: set[str] = set()
    since = days_ago(days)
    for table in tables:
        rows = query(
            f"SELECT DISTINCT day FROM {table} WHERE user_id = ? AND day >= ?",
            (current_user(), since))
        for row in rows:
            found.add(row["day"])
    return found
