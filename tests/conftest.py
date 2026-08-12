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

import hashlib
import math

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.config import settings
from db.base import Base
import db.models  # noqa: F401  — imported for the side effect of registering every table


@pytest.fixture(autouse=True)
def no_embedding_network(monkeypatch):
    """Cut the embedding HTTP call for every test. Autouse, because opting in is not a defence.

    The chat path embeds each query for hybrid retrieval, so any test that sends a message was
    silently calling the live Google API. That passed for months on available quota and then
    stopped: once the free tier returns 429 the retry honours Google's own ``retryDelay``, and
    a suite documented as needing no network hung for minutes per test.

    Only ``_google_batch`` — the function that actually opens the socket — is replaced.
    ``is_configured``, ``embed_query``, ``embed_documents``, the batching and every error path
    stay exactly as they are in production, so this removes the network without also removing
    the behaviour under test. Tests that stub at a higher level still override this, because
    monkeypatch applies theirs after.
    """
    def deterministic(texts: list[str], task_type: str) -> list[list[float]]:
        vectors = []
        for text in texts:
            seed = hashlib.sha256(f"{task_type}:{text}".encode()).digest()
            raw = [(seed[i % len(seed)] / 255.0) - 0.5 for i in range(settings.embedding_dim)]
            norm = math.sqrt(sum(v * v for v in raw)) or 1.0
            vectors.append([v / norm for v in raw])
        return vectors

    monkeypatch.setattr("services.embedding_service._google_batch", deterministic)


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
def client(engine, monkeypatch, tmp_path):
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

    # Two places deliberately open their own session rather than using the request-scoped one:
    # the streaming endpoint (the request's session is closed before the generator finishes) and
    # document ingestion (it runs as a background task after the response). Both must point at
    # the test database, or those code paths would silently touch the developer's workspace.db.
    monkeypatch.setattr("api.routers.conversations.SessionLocal", TestSession)
    monkeypatch.setattr("api.routers.documents.SessionLocal", TestSession)

    # Uploads land in a temp directory that vanishes with the test, so a run never leaves files
    # behind in data/uploads.
    monkeypatch.setattr("core.config.settings.upload_dir", tmp_path / "uploads")

    # The rate limiter is off by default here. A test that registers a user, creates a workspace
    # and sends a few messages would otherwise spend its allowance on setup and fail for a reason
    # it is not testing. ``test_security.py`` switches it back on and asserts it works.
    monkeypatch.setattr("core.config.settings.rate_limit_per_minute", 0)
    monkeypatch.setattr("core.config.settings.auth_rate_limit_per_minute", 0)

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class FakeLLM:
    """Stand-in for :class:`services.llm_service.LLMService`.

    Chat tests assert on persistence, ordering, titling and isolation — none of which need a real
    model, and all of which become flaky if a network call is involved. One live test in
    ``test_live_chat.py`` covers the real provider.
    """

    def __init__(self, reply: str = "A test reply.", title: str = "Test title"):
        self.reply = reply
        self.title = title
        self.last_used_model = "fake-model"
        self.last_used_provider = "fake"
        self.seen_messages: list[list[tuple[str, str]]] = []

    def chat(self, messages):
        self.seen_messages.append(messages)
        return self.reply

    def stream_chat(self, messages):
        self.seen_messages.append(messages)
        # Word by word, so a test can prove more than one chunk actually arrives.
        for word in self.reply.split(" "):
            yield word + " "

    def complete(self, system: str, user: str) -> str:
        return self.title


@pytest.fixture
def fake_llm(monkeypatch):
    """Replace the model client everywhere chat_service reaches for one."""
    stub = FakeLLM()
    monkeypatch.setattr("services.chat_service.get_llm", lambda **kwargs: stub)
    return stub


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
