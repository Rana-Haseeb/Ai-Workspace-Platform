"""FastAPI application factory.

Kept as a factory rather than a module-level ``app`` so tests can build an instance bound to
their own database without the import order mattering.
"""
from __future__ import annotations

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
    log.info(
        "API ready - %s, provider chain: %s",
        "SQLite" if settings.is_sqlite() else "PostgreSQL",
        " -> ".join(settings.provider_chain()),
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

    from api.routers import auth, workspaces

    app.include_router(auth.router)
    app.include_router(workspaces.router)

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
