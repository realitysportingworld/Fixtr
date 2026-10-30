"""
Test setup: the API runs against a throwaway SQLite file, rebuilt for every
test. These environment variables are set before the app is imported and
override backend/.env, so the tests never touch the real database.
"""
import os
import tempfile
import uuid
from pathlib import Path

_DB_FILE = Path(tempfile.mkdtemp(prefix="compapp-tests-")) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FILE.as_posix()}"
os.environ["SECRET_KEY"] = "t" * 64
os.environ["CORS_ORIGINS"] = '["http://localhost:8081"]'
os.environ["DEBUG"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.sql import sqltypes  # noqa: E402

# psycopg2 accepts UUIDs as strings; SQLite's Uuid binding doesn't. Mirror Postgres.
_orig_bind = sqltypes.Uuid.bind_processor


def _bind(self, dialect):
    proc = _orig_bind(self, dialect)
    if proc is None:
        return None
    return lambda v: proc(uuid.UUID(v) if isinstance(v, str) else v)


sqltypes.Uuid.bind_processor = _bind

from app.core import rate_limit  # noqa: E402
from app.db.base import Base, engine  # noqa: E402
import app.models.models  # noqa: E402,F401
from app.main import app  # noqa: E402

from tests.helpers import Api  # noqa: E402


@event.listens_for(engine, "connect")
def _foreign_keys_on(conn, _):
    conn.execute("PRAGMA foreign_keys=ON")


@pytest.fixture(autouse=True)
def fresh_state():
    """Empty database and rate limiters for every test."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    for limiter in (rate_limit.login_failures_by_email, rate_limit.login_failures_by_ip,
                    rate_limit.registrations_by_ip):
        limiter._events.clear()
    yield


def _signed_up(username: str) -> TestClient:
    client = TestClient(app)
    r = client.post("/api/v1/auth/register", json={
        "email": f"{username}@example.com", "username": username, "password": "longenough1",
    })
    assert r.status_code == 201, r.text
    client.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return client


@pytest.fixture
def anon() -> TestClient:
    return TestClient(app)


@pytest.fixture
def api() -> Api:
    """Signed in as 'admin', who owns the competitions the tests create."""
    return Api(_signed_up("admin"))


@pytest.fixture
def other() -> Api:
    """A second signed-in user, for read-only / access checks."""
    return Api(_signed_up("viewer"))
