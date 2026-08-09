"""FastAPI application factory.

Kept as a factory rather than a module-level ``app`` so tests can build an instance bound to
their own database without the import order mattering.
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from core.logging import get_logger
from db.base import Base, engine
import db.models  # noqa: F401  — registers every table before create_all

log = get_logger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)

    # Import the model client at boot rather than on the first chat message.
    #
    # Measured, not guessed: importing langchain_openai takes ~18 seconds the first time, and
    # llm_service imports it lazily inside _client_for. That put the whole 18s inside the first
    # user's request — a message that should take 0.2s was recorded at 20.7s. Paying it here
    # costs startup time nobody is watching instead of the first impression somebody is.
    started = time.perf_counter()
    try:
        import langchain_openai  # noqa: F401
        log.info("Model client warmed in %.1fs", time.perf_counter() - started)
    except ImportError:  # pragma: no cover — only if the dependency is genuinely absent
        log.warning("langchain_openai is not installed; chat will fail until it is")

    log.info(
        "API ready - %s, provider chain: %s",
        "SQLite" if settings.is_sqlite() else "PostgreSQL",
        " -> ".join(settings.provider_chain()) or "none configured",
    )
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Workspace Platform",
        version="0.1.0",
        summary="Multi-user AI workspaces with persistent memory and document intelligence.",
        lifespan=lifespan,
    )

    # In development the SPA runs on its own port; in production uvicorn serves the built SPA
    # from this same origin, so CORS is a development-only concern. allow_credentials is
    # required for the session cookie to survive a cross-origin request.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from api.routers import auth, conversations, workspaces

    app.include_router(auth.router)
    app.include_router(workspaces.router)
    app.include_router(conversations.router)

    @app.get("/api/health", tags=["meta"])
    def health() -> dict:
        """Liveness probe. Deliberately reports no secrets and no connection strings."""
        return {
            "status": "ok",
            "database": "sqlite" if settings.is_sqlite() else "postgresql",
            "providers_configured": len(settings.provider_chain()),
        }

    return app


app = create_app()
