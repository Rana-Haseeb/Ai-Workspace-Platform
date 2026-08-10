"""Engine, session factory, and declarative base.

One set of models serves two dialects. SQLite gets ``check_same_thread=False`` because FastAPI
serves requests on a threadpool and a session may be touched by a different thread than the one
that opened the connection. Postgres gets pooling with ``pool_pre_ping`` so that Supabase's
connection pooler dropping an idle connection surfaces as a transparent reconnect rather than a
500 on the next request.

Nothing else in the codebase knows which database is underneath. That is the point, and it is
what makes "migrate from SQLite to Postgres" a change to one environment variable.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from core.config import settings


def normalise_database_url(url: str) -> str:
    """Point a bare ``postgresql://`` URL at psycopg 3.

    Every hosted provider — Neon, Supabase, Aiven — hands out a URL starting ``postgresql://``,
    and SQLAlchemy maps that to **psycopg2**, which this project does not install. Pasting the
    provider's string verbatim would therefore fail at deployment with a ModuleNotFoundError,
    which is a miserable thing to discover on the day you deploy.

    Rewriting the scheme here means the string can be copied straight from the dashboard.
    ``postgresql+psycopg://`` and other explicit drivers are left alone.
    """
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        # Heroku-style scheme, still emitted by some providers.
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


def engine_kwargs(url: str) -> dict:
    """Connection arguments appropriate to the dialect in ``url``."""
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    # pool_pre_ping matters more than usual on serverless Postgres: Neon scales to zero after
    # a few minutes idle, so the first request after a quiet spell finds a dead connection.
    # Pre-ping turns that into a transparent reconnect instead of a 500.
    return {"pool_pre_ping": True, "pool_size": 5, "max_overflow": 10, "pool_recycle": 300}


DATABASE_URL = normalise_database_url(settings.database_url)
engine = create_engine(DATABASE_URL, **engine_kwargs(DATABASE_URL))
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for every model in :mod:`db.models`."""


def get_session() -> Session:
    """A new session. Callers are responsible for closing it.

    FastAPI routes use the ``get_db`` dependency in :mod:`api.deps` instead, which closes the
    session for them; this is for scripts and tests.
    """
    return SessionLocal()
