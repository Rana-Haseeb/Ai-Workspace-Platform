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
