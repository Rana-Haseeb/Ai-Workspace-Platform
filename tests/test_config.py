"""Configuration behaves the way the deployment story assumes it does."""
from __future__ import annotations

import os

from core.config import PROVIDERS, Settings, settings


def test_sqlite_is_the_local_default():
    """Without a DATABASE_URL, everything runs on a local SQLite file."""
    assert settings.is_sqlite()
    assert settings.database_url.startswith("sqlite")


def test_no_secret_has_a_hardcoded_default():
    """A real secret must come from the environment, never from source."""
    assert settings.jwt_secret == "" or len(settings.jwt_secret) >= 16
    for provider in PROVIDERS.values():
        # Providers name the env var holding their key; they must never carry the key itself.
        assert provider.api_key_env.endswith("_API_KEY") or "_API_KEY_" in provider.api_key_env


def test_provider_chain_drops_backends_with_no_key():
    """Listing every provider in the fallback chain is free — unconfigured ones are filtered."""
    chain = settings.provider_chain()
    assert chain[0] == settings.provider
    for name in chain[1:]:
        assert os.getenv(PROVIDERS[name].api_key_env), f"{name} in chain without a key"


def test_postgres_url_switches_the_dialect_flag():
    """The one env var that moves the whole platform from SQLite to Postgres."""
    os.environ["DATABASE_URL"] = "postgresql://user:pw@host:5432/db"
    try:
        assert Settings().is_sqlite() is False
    finally:
        del os.environ["DATABASE_URL"]


# ------------------------------------------------------- production URL handling
def test_provider_urls_are_pointed_at_psycopg3():
    """A URL copied straight from Neon, Supabase or Aiven must work as pasted.

    Every provider hands out ``postgresql://``, which SQLAlchemy maps to psycopg2 — a package
    this project does not install. Without the rewrite, deployment fails with
    ModuleNotFoundError on the first request, which is a miserable way to find out.
    """
    from db.base import normalise_database_url

    neon = "postgresql://user:pw@ep-x.aws.neon.tech/neondb?sslmode=require"
    assert normalise_database_url(neon).startswith("postgresql+psycopg://")
    # The rest of the URL, including the query string, is untouched.
    assert normalise_database_url(neon).endswith("/neondb?sslmode=require")


def test_heroku_style_scheme_is_also_handled():
    from db.base import normalise_database_url

    assert normalise_database_url("postgres://u:p@h/db").startswith("postgresql+psycopg://")


def test_an_explicit_driver_is_left_alone():
    from db.base import normalise_database_url

    for url in [
        "postgresql+psycopg://u:p@h/db",
        "postgresql+asyncpg://u:p@h/db",
        "sqlite:///./workspace.db",
    ]:
        assert normalise_database_url(url) == url


def test_serverless_postgres_gets_connection_recycling():
    """Neon scales to zero when idle, so a pooled connection can be dead on arrival."""
    from db.base import engine_kwargs

    postgres = engine_kwargs("postgresql+psycopg://u:p@h/db")
    assert postgres["pool_pre_ping"] is True
    assert postgres["pool_recycle"] > 0
    assert "pool_pre_ping" not in engine_kwargs("sqlite:///./x.db")
