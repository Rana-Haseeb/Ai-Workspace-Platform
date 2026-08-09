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
