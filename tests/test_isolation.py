"""
One user must never see another user's health record.

Two kinds of test here. The first actually runs the app as two people and
checks nothing crosses over. The second reads the source: it walks every
SQL string in the codebase and fails if one touches a table of personal
data without filtering on the owner.

The second one exists because the first can only catch the paths it
thinks to try. A query added later to a new agent would pass every
behavioural test in this suite while quietly serving someone else's
numbers, and nothing about reading the code would make that obvious.
"""
import ast
import pathlib

import pytest

from app.store import db, users

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCES = sorted((ROOT / "app").rglob("*.py")) + \
          sorted((ROOT / "scripts").rglob("*.py"))

# Statements that are meant to run across every account. Each one is
# listed here deliberately, so adding another is a visible decision.
UNSCOPED_ON_PURPOSE = {
    # Tests wipe the whole database between runs.
    "DELETE FROM {table}",
    # Accounts themselves are not owned by a user; they are the user.
    "SELECT * FROM users WHERE email = ?",
    "SELECT * FROM users WHERE id = ?",
    "SELECT COUNT(*) n FROM users",
    "INSERT INTO users (email, name, password_hash, created_at) "
    "VALUES (?, ?, ?, ?)",
}

VERBS = ("select", "insert", "update", "delete")


def _string_literals(tree: ast.AST):
    """Every string in a file, with f-string literal parts stitched in."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value
        elif isinstance(node, ast.JoinedStr):
            parts = []
            for piece in node.values:
                if isinstance(piece, ast.Constant):
                    parts.append(str(piece.value))
                elif isinstance(piece, ast.FormattedValue):
                    # The value is not known statically. Keep a marker so
                    # "FROM {table}" still reads as touching a table.
                    parts.append("{table}")
            yield "".join(parts)


def _sql_statements():
    """(file, statement) for every SQL string in the app."""
    for path in SOURCES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for text in _string_literals(tree):
            flat = " ".join(text.split())
            if flat.lower().startswith(VERBS):
                yield path.relative_to(ROOT).as_posix(), flat


def test_every_query_on_personal_data_filters_by_owner():
    unscoped = []
    for where, statement in _sql_statements():
        if statement in UNSCOPED_ON_PURPOSE:
            continue
        touches = any(f" {t}" in f" {statement.lower()} "
                      for t in db.OWNED_TABLES)
        placeholder = "{table}" in statement
        if (touches or placeholder) and "user_id" not in statement:
            unscoped.append(f"{where}: {statement}")

    assert not unscoped, (
        "These statements read or write personal data without saying whose:\n  "
        + "\n  ".join(unscoped))


def test_the_check_above_would_actually_catch_something():
    """A guard is worth nothing if it cannot fail."""
    bad = "SELECT day, hours FROM sleep ORDER BY day DESC"
    assert "user_id" not in bad
    assert any(f" {t}" in f" {bad.lower()} " for t in db.OWNED_TABLES)


# --- and now the behavioural half ---------------------------------------

@pytest.fixture
def two_people(clean_db):
    db.delete_everything()
    a = users.create("ashnoor@example.com", "Ashnoor", "a-good-password")
    b = users.create("kanan@example.com", "Kanan", "another-password")
    yield a, b
    db.delete_everything()


def _as(user):
    db.CURRENT_USER.set(user["id"])


def test_one_persons_logging_is_invisible_to_another(two_people):
    a, b = two_people

    _as(a)
    db.add_water(6)
    db.add_meal("biryani", 480)
    db.add_sleep(5.5)
    db.add_symptom("headache after lunch")

    _as(b)
    assert db.query("SELECT COUNT(*) n FROM water WHERE user_id = ?",
                    (b["id"],))[0]["n"] == 0
    assert db.all_series(7)["water"]["points"][-1]["value"] is None
    assert db.logged_days() == set()


def test_each_person_sees_their_own_numbers(two_people):
    a, b = two_people

    _as(a)
    db.add_water(6)
    _as(b)
    db.add_water(2)

    _as(a)
    assert db.all_series(7)["water"]["points"][-1]["value"] == 6
    _as(b)
    assert db.all_series(7)["water"]["points"][-1]["value"] == 2


def test_the_agents_answer_for_the_signed_in_person(two_people):
    from app.main import build_bus
    a, b = two_people

    _as(a)
    db.add_water(7)
    db.add_sleep(8)

    _as(b)
    bus = build_bus()
    assert bus.get("hydration").report()["glasses_today"] == 0
    assert bus.get("sleep").report()["has_data"] is False

    _as(a)
    assert bus.get("hydration").report()["glasses_today"] == 7
    assert bus.get("sleep").report()["has_data"] is True


def test_nobody_signed_in_sees_nothing(two_people):
    a, _ = two_people
    _as(a)
    db.add_water(5)

    db.CURRENT_USER.set(0)
    assert db.all_series(7)["water"]["points"][-1]["value"] is None
    assert db.get_profile() == {}
