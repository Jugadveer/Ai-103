"""
Accounts, sessions, and the gate in front of the health data.

The test that matters most is test_every_data_endpoint_requires_signing_in.
It walks the route table rather than listing paths by hand, so an endpoint
added later is covered the day it is written. Anything genuinely public
has to be named in PUBLIC below, which makes leaving a route open a
deliberate line in a diff instead of an oversight.
"""
import time

import pytest

from app import auth
from app.core.errors import ValidationError
from app.store import db, users
from tests.conftest import ACCOUNT

# Open on purpose. The page itself, its assets, the service worker, a
# health check with no personal data in it, the list of agent names and
# descriptions, and the three endpoints you need before you have a
# session.
PUBLIC = {
    "/", "/manifest.webmanifest", "/sw.js", "/static",
    "/api/health", "/api/agents",
    "/api/auth/me", "/api/auth/signup", "/api/auth/login", "/api/auth/logout",
}


def _api_routes():
    from app.main import app
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) - {"HEAD", "OPTIONS"}
        if path.startswith("/api") and methods:
            yield path, sorted(methods)[0]


def test_every_data_endpoint_requires_signing_in(anon_client):
    open_to_anyone = []
    for path, method in _api_routes():
        if path in PUBLIC:
            continue
        reply = anon_client.request(method, path, json={})
        if reply.status_code != 401:
            open_to_anyone.append(f"{method} {path} -> {reply.status_code}")

    assert not open_to_anyone, (
        "These endpoints answered without a session:\n  "
        + "\n  ".join(open_to_anyone))


def test_the_public_list_is_not_hiding_a_data_endpoint():
    """Every path in PUBLIC must actually exist, so the list cannot rot."""
    paths = {path for path, _ in _api_routes()} | {"/", "/sw.js",
                                                   "/manifest.webmanifest",
                                                   "/static"}
    assert PUBLIC <= paths, f"PUBLIC names routes that are gone: {PUBLIC - paths}"


# --- signing up ----------------------------------------------------------

def test_signup_creates_an_account_and_signs_you_in(anon_client):
    reply = anon_client.post("/api/auth/signup", json={
        "email": "New.Person@Example.com", "name": "New Person",
        "password": "long-enough-password"})
    assert reply.status_code == 200
    assert reply.json()["ok"] is True
    # Stored lowercase, so signing in with a different case still works.
    assert reply.json()["user"]["email"] == "new.person@example.com"
    assert anon_client.get("/api/auth/me").json()["user"]["name"] == "New Person"
    assert anon_client.get("/api/dashboard").status_code == 200


def test_signup_can_fill_the_account_with_sample_data(anon_client):
    anon_client.post("/api/auth/signup", json={
        "email": "curious@example.com", "name": "Curious",
        "password": "long-enough-password", "sample_data": True})
    history = anon_client.get("/api/history?days=30").json()
    logged = [p for p in history["sleep"]["points"] if p["value"] is not None]
    assert len(logged) > 20


def test_a_new_account_without_sample_data_is_empty(anon_client):
    anon_client.post("/api/auth/signup", json={
        "email": "empty@example.com", "name": "Empty",
        "password": "long-enough-password"})
    history = anon_client.get("/api/history?days=30").json()
    assert all(p["value"] is None for p in history["sleep"]["points"])


@pytest.mark.parametrize("payload,expected", [
    ({"email": "not-an-email", "name": "A", "password": "long-enough"},
     "email address"),
    ({"email": "a@b.co", "name": "  ", "password": "long-enough"},
     "call you"),
    ({"email": "a@b.co", "name": "A", "password": "short"},
     "at least 8 characters"),
])
def test_signup_says_what_is_wrong(anon_client, payload, expected):
    reply = anon_client.post("/api/auth/signup", json=payload)
    assert reply.status_code == 400
    assert expected in " ".join(reply.json()["errors"])


def test_signup_refuses_an_email_already_taken(anon_client):
    reply = anon_client.post("/api/auth/signup", json={
        "email": ACCOUNT["email"], "name": "Impostor",
        "password": "long-enough-password"})
    assert reply.status_code == 400
    assert "already exists" in " ".join(reply.json()["errors"])


# --- signing in ----------------------------------------------------------

def test_login_with_the_right_password(anon_client):
    reply = anon_client.post("/api/auth/login", json={
        "email": ACCOUNT["email"], "password": ACCOUNT["password"]})
    assert reply.status_code == 200
    assert anon_client.get("/api/dashboard").status_code == 200


def test_login_with_the_wrong_password_is_refused(anon_client):
    reply = anon_client.post("/api/auth/login", json={
        "email": ACCOUNT["email"], "password": "not-the-password"})
    assert reply.status_code == 401
    assert anon_client.get("/api/dashboard").status_code == 401


def test_a_wrong_password_and_an_unknown_email_look_identical(anon_client):
    """Otherwise the form tells a stranger which emails are registered."""
    wrong = anon_client.post("/api/auth/login", json={
        "email": ACCOUNT["email"], "password": "not-the-password"})
    unknown = anon_client.post("/api/auth/login", json={
        "email": "nobody@example.com", "password": "not-the-password"})
    assert wrong.status_code == unknown.status_code
    assert wrong.json()["errors"] == unknown.json()["errors"]


def test_logout_ends_the_session(client):
    assert client.get("/api/dashboard").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/dashboard").status_code == 401


def test_me_returns_nobody_before_signing_in(anon_client):
    assert anon_client.get("/api/auth/me").json()["user"] is None


# --- the cookie ----------------------------------------------------------

def test_the_session_cookie_is_not_readable_by_scripts(anon_client):
    reply = anon_client.post("/api/auth/login", json={
        "email": ACCOUNT["email"], "password": ACCOUNT["password"]})
    cookie = reply.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


def test_an_edited_cookie_is_rejected(anon_client, clean_db):
    """Change the user id in the token and the signature stops matching."""
    real = auth.make_token(1)
    user_id, expires, signature = real.split(".")
    forged = f"{int(user_id) + 1}.{expires}.{signature}"
    assert auth.read_token(forged) is None
    assert auth.read_token(real) == 1


def test_an_expired_token_is_rejected():
    payload = f"7.{int(time.time()) - 60}"
    expired = f"{payload}.{auth._sign(payload)}"
    assert auth.read_token(expired) is None


def test_nonsense_in_the_cookie_is_rejected():
    for junk in ["", "abc", "1.2", "1.2.3.4", "x.y.z", None]:
        assert auth.read_token(junk) is None


# --- passwords -----------------------------------------------------------

def test_the_password_is_never_stored(clean_db):
    row = users.find_by_email(ACCOUNT["email"])
    assert ACCOUNT["password"] not in str(row)
    assert row["password_hash"].startswith("scrypt$")


def test_the_same_password_hashes_differently_every_time():
    """A shared salt would let one cracked hash unlock every match."""
    a = users.hash_password("the same password")
    b = users.hash_password("the same password")
    assert a != b
    assert users.check_password("the same password", a)
    assert users.check_password("the same password", b)


def test_a_wrong_password_does_not_verify():
    stored = users.hash_password("correct horse")
    assert not users.check_password("battery staple", stored)
    assert not users.check_password("", stored)


def test_a_corrupt_hash_fails_closed():
    for broken in ["", "nonsense", "scrypt$bad", "md5$1$2$3$aa$bb"]:
        assert not users.check_password("anything", broken)


def test_creating_a_duplicate_account_raises(clean_db):
    with pytest.raises(ValidationError):
        users.create(ACCOUNT["email"], "Someone Else", "another-password")


def test_email_is_matched_regardless_of_case_and_spacing(clean_db):
    found = users.find_by_email(f"  {ACCOUNT['email'].upper()}  ")
    assert found is not None
