"""Shared test fixtures. Every test runs against a throwaway database."""
import os

os.environ["MOCK_MODE"] = "true"
os.environ["DB_PATH"] = "test_health.db"

import pytest

from app.core import logging as log
from app.main import build_bus
from app.store import db

log.ENABLED = False  # keep test output readable


@pytest.fixture
def clean_db():
    """An initialised, empty database."""
    db.init_db()
    db.clear_all()
    yield db
    db.clear_all()


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
def client(clean_db):
    """FastAPI test client."""
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c
