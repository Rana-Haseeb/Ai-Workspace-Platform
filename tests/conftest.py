"""Shared test fixtures.

Every test gets its own in-memory SQLite database. That choice buys three things: tests need no
network and no running Postgres, a full run stays in the low seconds, and no test can leak state
into another because the database ceases to exist when the fixture tears down.

``StaticPool`` matters more than it looks. SQLAlchemy's default pool hands out a *new* connection
per checkout, and every new connection to ``sqlite://`` is a brand-new empty database — so the
tables created in the fixture would be invisible to the code under test. StaticPool keeps one
connection for the life of the engine, which is what makes the in-memory database shared.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.base import Base
import db.models  # noqa: F401  — imported for the side effect of registering every table


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite ships with foreign-key enforcement OFF. Without this, ON DELETE CASCADE is silently
    # ignored and a test asserting that deletion cascades would pass for the wrong reason.
    @event.listens_for(eng, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(eng)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def db(engine):
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(engine, monkeypatch):
    """A TestClient whose requests run against the test database.

    ``get_db`` is overridden rather than the engine being swapped globally, because the override
    is exactly the seam FastAPI provides for this and it leaves the real application untouched.
    Each request gets its own session from the same in-memory database, which mirrors production
    (a session per request) instead of sharing one session across the whole test.
    """
    from fastapi.testclient import TestClient

    # A fixed signing key so tokens stay valid across the requests inside one test, and so a
    # test never depends on whatever happens to be in the developer's .env.
    monkeypatch.setattr("core.config.settings.jwt_secret", "test-secret-key-not-for-real-use")

    from api.deps import get_db
    from api.main import create_app

    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def make_user(client):
    """Register a user and return a callable-free handle: their id, email, and auth headers.

    Returns headers rather than relying on the client's cookie jar so that two users can be
    active in one test — which is precisely what the isolation test needs.
    """
    counter = {"n": 0}

    def _make(email: str | None = None, password: str = "correct-horse-battery"):
        counter["n"] += 1
        address = email or f"user{counter['n']}@example.com"
        response = client.post(
            "/api/auth/register", json={"email": address, "password": password}
        )
        assert response.status_code == 201, response.text
        body = response.json()
        return {
            "id": body["user"]["id"],
            "email": address,
            "password": password,
            "headers": {"Authorization": f"Bearer {body['access_token']}"},
        }

    return _make
