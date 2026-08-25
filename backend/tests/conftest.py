"""Test fixtures.

The database URL is set before any application module is imported, because
`app.db` builds its engine at import time from the settings singleton. Each test
run therefore gets a throwaway SQLite file rather than touching the demo
database someone might be mid-recording with.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_TMPDIR = tempfile.mkdtemp(prefix="atlas-tests-")
os.environ["ATLAS_DATABASE_URL"] = f"sqlite:///{Path(_TMPDIR) / 'test.db'}"
os.environ["ATLAS_DEMO_MODE"] = "true"
os.environ.pop("ATLAS_API_KEY", None)

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.services import faults
from seed.seed import reset_database


@pytest.fixture(autouse=True)
def fresh_database():
    """Every test starts from the seeded state.

    Reseeding per test rather than per session keeps the write tests from
    leaking state into each other -- a test that reduces PO 1847 must not change
    what the next test reads.
    """
    faults.clear()
    reset_database()
    yield
    faults.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
