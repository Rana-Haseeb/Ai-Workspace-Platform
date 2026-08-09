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


def engine_kwargs(url: str) -> dict:
    """Connection arguments appropriate to the dialect in ``url``."""
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_pre_ping": True, "pool_size": 5, "max_overflow": 10}


engine = create_engine(settings.database_url, **engine_kwargs(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for every model in :mod:`db.models`."""


def get_session() -> Session:
    """A new session. Callers are responsible for closing it.

    FastAPI routes use the ``get_db`` dependency in :mod:`api.deps` instead, which closes the
    session for them; this is for scripts and tests.
    """
    return SessionLocal()
