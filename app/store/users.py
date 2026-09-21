"""
Accounts.

Passwords are hashed with scrypt from the standard library. Nothing is
installed for this: scrypt is deliberately slow and memory-hard, which is
the whole point, and hashlib has had it since Python 3.6. A stored value
looks like

    scrypt$16384$8$1$<salt hex>$<hash hex>

so the work factors travel with the hash and can be raised later without
invalidating anyone's existing password.

The plain password is never written anywhere: not to the database, not to
a log line, not into an error message.
"""
import hashlib
import hmac
import re
import secrets
from datetime import datetime

from app.core.errors import ValidationError
from app.store import db

# scrypt cost. n is the big one; 16384 takes roughly 60ms per attempt
# here, which is slow enough to make guessing expensive and fast enough
# that signing in still feels instant.
N, R, P = 16384, 8, 1
KEY_LEN = 32

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
MIN_PASSWORD = 8


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P,
                            dklen=KEY_LEN)
    return f"scrypt${N}${R}${P}${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        kind, n, r, p, salt_hex, want = stored.split("$")
        if kind != "scrypt":
            return False
        got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex),
                             n=int(n), r=int(r), p=int(p), dklen=KEY_LEN)
    except (ValueError, TypeError):
        return False
    # Constant time, so the comparison cannot be timed to leak the hash.
    return hmac.compare_digest(got.hex(), want)


def normalise_email(email: str) -> str:
    return (email or "").strip().lower()


def validate_signup(email: str, name: str, password: str) -> list[str]:
    problems = []
    if not EMAIL.match(normalise_email(email)):
        problems.append("That does not look like an email address.")
    if not (name or "").strip():
        problems.append("Please tell us what to call you.")
    if len(password or "") < MIN_PASSWORD:
        problems.append(
            f"Use at least {MIN_PASSWORD} characters for the password.")
    return problems


def create(email: str, name: str, password: str) -> dict:
    """Make an account. Raises ValidationError if the email is taken."""
    email = normalise_email(email)
    if find_by_email(email):
        raise ValidationError("An account with that email already exists.")
    row = {
        "email": email,
        "name": (name or "").strip()[:60],
        "password_hash": hash_password(password),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    sql = ("INSERT INTO users (email, name, password_hash, created_at) "
           "VALUES (?, ?, ?, ?)")
    params = (row["email"], row["name"], row["password_hash"],
              row["created_at"])
    if db.POSTGRES:
        with db.connect() as s:
            row["id"] = s.run(sql + " RETURNING id", params).fetchone()["id"]
    else:
        with db.connect() as s:
            row["id"] = s.run(sql, params).lastrowid
    return public(row)


def find_by_email(email: str) -> dict | None:
    rows = db.query("SELECT * FROM users WHERE email = ?",
                    (normalise_email(email),))
    return rows[0] if rows else None


def find_by_id(user_id: int) -> dict | None:
    rows = db.query("SELECT * FROM users WHERE id = ?", (user_id,))
    return rows[0] if rows else None


def authenticate(email: str, password: str) -> dict | None:
    """Return the user on a correct password, None otherwise.

    The same None covers a missing account and a wrong password, and the
    hash still runs when the account does not exist, so the response time
    does not reveal which emails are registered.
    """
    user = find_by_email(email)
    stored = user["password_hash"] if user else hash_password("no such user")
    if check_password(password or "", stored) and user:
        return public(user)
    return None


def public(user: dict) -> dict:
    """Only the fields safe to send to the browser."""
    return {"id": user["id"], "email": user["email"], "name": user["name"]}


def count() -> int:
    return db.query("SELECT COUNT(*) n FROM users")[0]["n"]
