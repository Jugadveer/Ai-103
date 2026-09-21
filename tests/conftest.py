"""Shared test fixtures. Every test runs against a throwaway database."""
import os

os.environ["MOCK_MODE"] = "true"
os.environ["DB_PATH"] = "test_health.db"
os.environ["SECRET_KEY"] = "test-key-not-used-anywhere-real"

import pytest

from app.core import logging as log
from app.main import build_bus
from app.store import db, users

log.ENABLED = False  # keep test output readable

# Every row belongs to an account now, so the tests need one to be. They
# all run as this person unless a test deliberately makes others.
ACCOUNT = {"email": "tester@example.com", "name": "Tester",
           "password": "a-test-password"}


@pytest.fixture
def clean_db():
    """An initialised, empty database with one signed-in account."""
    db.init_db()
    db.delete_everything()
    user = users.create(**ACCOUNT)
    db.CURRENT_USER.set(user["id"])
    yield db
    db.delete_everything()
    db.CURRENT_USER.set(0)


@pytest.fixture
def bus(clean_db):
    """A full agent mesh over an empty database."""
    return build_bus()


@pytest.fixture
def seeded_bus(clean_db):
    """A full agent mesh over the demo dataset."""
    from scripts.seed import seed_demo_data
    seed_demo_data()
    return build_bus()


@pytest.fixture
def anon_client(clean_db):
    """A client with no session, for checking that the gate is shut."""
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client(anon_client):
    """A signed-in client. Carries the session cookie like a browser."""
    reply = anon_client.post("/api/auth/login", json={
        "email": ACCOUNT["email"], "password": ACCOUNT["password"]})
    assert reply.status_code == 200, reply.text
    return anon_client
