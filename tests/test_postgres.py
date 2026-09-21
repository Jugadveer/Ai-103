"""
The Postgres path, checked without a Postgres.

The app runs on SQLite locally and Postgres when deployed, from one set
of SQL strings. That is only safe if the strings are actually legal in
both, and the differences are the quiet kind: a subquery in FROM needs an
alias in Postgres and not in SQLite, AUTOINCREMENT is not a Postgres
word, AVG comes back as a Decimal rather than a float.

None of that shows up in the test suite, which runs on SQLite. So these
tests parse every statement in the codebase with a Postgres parser, and
check the handful of places where the two backends are spelled
differently. A broken deploy is otherwise the first time anyone finds
out, and by then it is in front of the team.
"""
import ast
import pathlib

import pytest

from app.store import db

sqlglot = pytest.importorskip(
    "sqlglot", reason="pip install sqlglot to check the Postgres dialect")

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCES = sorted((ROOT / "app").rglob("*.py")) + \
          sorted((ROOT / "scripts").rglob("*.py"))

STARTS = ("select", "insert into", "update ", "delete from", "create")


def _literals(tree):
    """Every string, f-strings stitched, their fragments not counted twice."""
    inside_an_fstring = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            inside_an_fstring.update(id(piece) for piece in node.values)

    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            # The interpolated part is a table or column name chosen at
            # run time. Any real one will do for a syntax check.
            yield "".join(
                str(piece.value) if isinstance(piece, ast.Constant) else "meals"
                for piece in node.values)
        elif (isinstance(node, ast.Constant) and isinstance(node.value, str)
              and id(node) not in inside_an_fstring):
            yield node.value


def _statements():
    yield from (("app/store/db.py SCHEMA", s.strip())
                for s in db.SCHEMA.format(id="SERIAL PRIMARY KEY").split(";")
                if s.strip())
    for path in SOURCES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for text in _literals(tree):
            flat = " ".join(text.split())
            if flat.lower().startswith(STARTS) and "{id}" not in flat:
                yield path.relative_to(ROOT).as_posix(), flat


def test_every_statement_is_valid_postgres():
    from sqlglot.errors import ParseError

    broken = []
    total = 0
    for where, statement in _statements():
        total += 1
        try:
            sqlglot.parse_one(statement.replace("?", "%s"), read="postgres")
        except ParseError as exc:
            broken.append(f"{where}\n    {statement[:150]}"
                          f"\n    {str(exc).splitlines()[0][:150]}")

    assert total > 40, f"only found {total} statements, the scan is broken"
    assert not broken, ("These do not parse as Postgres:\n  "
                        + "\n  ".join(broken))


def test_every_statement_is_valid_sqlite_too():
    """Both backends, one set of strings. Neither is allowed to be an
    afterthought."""
    from sqlglot.errors import ParseError

    broken = []
    for where, statement in _statements():
        try:
            sqlglot.parse_one(statement, read="sqlite")
        except ParseError as exc:
            broken.append(f"{where}: {str(exc).splitlines()[0][:120]}")
    assert not broken, "\n  ".join(broken)


def test_a_subquery_in_from_is_aliased():
    """
    Postgres rejects an unaliased subquery in FROM; SQLite accepts it.
    The personal-best query is the only place this applies, and it passed
    every test on SQLite while being invalid on the deployed backend.

    sqlglot parses the unaliased form happily, so it cannot catch this
    for us. Check our own SQL instead: find the subquery and assert the
    closing bracket is followed by a name.
    """
    import re
    found = [s for _, s in _statements() if "FROM (" in s.upper()]
    assert found, "the personal-best subquery has gone missing"
    for statement in found:
        tail = statement[statement.rindex(")") + 1:].strip()
        assert re.match(r"^[A-Za-z_]\w*", tail), (
            f"subquery needs an alias for Postgres: {statement}")


# --- the shim between the two --------------------------------------------

def test_placeholders_are_rewritten_only_for_postgres(monkeypatch):
    sql = "SELECT 1 FROM meals WHERE user_id = ? AND day = ?"
    monkeypatch.setattr(db, "POSTGRES", False)
    assert db._placeholders(sql) == sql
    monkeypatch.setattr(db, "POSTGRES", True)
    assert db._placeholders(sql) == \
        "SELECT 1 FROM meals WHERE user_id = %s AND day = %s"


def test_the_schema_differs_in_exactly_one_place():
    """If a second difference appears, it should be a deliberate change."""
    lite = db.SCHEMA.format(id="INTEGER PRIMARY KEY AUTOINCREMENT")
    post = db.SCHEMA.format(id="SERIAL PRIMARY KEY")
    assert "AUTOINCREMENT" in lite and "AUTOINCREMENT" not in post
    assert "SERIAL" in post and "SERIAL" not in lite
    assert lite.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY") \
        == post


def test_every_owned_table_carries_its_owner():
    schema = db.SCHEMA.format(id="SERIAL PRIMARY KEY")
    for table in db.OWNED_TABLES:
        block = schema.split(f"CREATE TABLE IF NOT EXISTS {table} (")[1] \
                      .split(");")[0]
        assert "user_id" in block, f"{table} has no owner column"


def test_users_is_not_treated_as_owned():
    """It holds the owners; it cannot belong to one."""
    assert "users" not in db.OWNED_TABLES


@pytest.mark.parametrize("stored,expected", [
    (2, 2),                          # SUM of integers, both backends
    (7.25, 7.2),                     # SUM of reals, SQLite
    (__import__("decimal").Decimal("3.6666"), 3.7),   # AVG, Postgres
])
def test_a_reading_survives_whichever_type_the_backend_returns(
        monkeypatch, clean_db, stored, expected):
    """
    Postgres hands back AVG as a Decimal, SQLite as a float, and a SUM of
    integers as an int on both. series() has to leave whole numbers whole
    and round the rest without knowing which backend it is on. A Decimal
    reaching the browser would serialise as a string and the chart would
    draw nothing.
    """
    import json
    monkeypatch.setattr(db, "query",
                        lambda sql, params=(): [{"day": db.today(), "v": stored}])

    today = db.series("mood", 3)["points"][-1]
    assert today["value"] == expected
    assert isinstance(today["value"], (int, float))
    # And it has to survive the trip to the page.
    assert json.loads(json.dumps(today))["value"] == expected


# --- a bug that has happened twice ----------------------------------------

def test_no_source_file_contains_a_control_character():
    """
    Twice now a regex has reached the repository with its \b word
    boundaries turned into literal backspace characters, written by a
    patch script whose replacement text was not a raw string. The regex
    still compiles. It just quietly matches nothing, so a guardrail looks
    present in review and is inert at runtime.

    Backspace is never legitimate in this codebase, so it is worth one
    assertion rather than another afternoon.
    """
    import unicodedata
    offenders = []
    for path in SOURCES + sorted((ROOT / "tests").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for index, char in enumerate(text):
            if unicodedata.category(char) == "Cc" and char not in "\n\t\r":
                line = text[:index].count("\n") + 1
                offenders.append(
                    f"{path.relative_to(ROOT).as_posix()}:{line} "
                    f"U+{ord(char):04X}")
    assert not offenders, ("Control characters in source, probably a \b "
                           "eaten by a non-raw string:\n  "
                           + "\n  ".join(offenders))
