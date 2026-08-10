"""Environment-based configuration. No hard-coded secrets.

Ported from the Week 4 multi-agent platform, with two changes that follow from Week 5 being a
*platform* rather than a workflow:

1. **The agent-graph budgets are gone.** Week 4 capped revision cycles, research rounds and
   parallel fan-out because a graph can loop. Week 5 has no graph — a request is one chat turn —
   so those knobs would be dead configuration. What replaces them is per-workspace assistant
   configuration held in the ``settings`` table, because in a multi-user platform the model,
   temperature and token ceiling belong to the user's workspace, not to the deployment.

2. **The provider failover survives intact.** A live Week 4 deployment with one key hit its rate
   limit mid-run: 216 calls attempted, 164 refused. Multi-user traffic makes that more likely,
   not less, so the cross-provider chain is carried over unchanged.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Project root = parent of the ``core`` package.
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _csv(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


class ProviderConfig(BaseModel):
    """A single OpenAI-compatible LLM provider."""

    label: str
    base_url: str
    api_key_env: str
    default_model: str
    models: list[str]                     # in-provider fallback chain, best first
    probe_models: list[str] = []          # candidates for scripts/probe_providers.py
    # USD per 1M tokens, for the dashboard's measured cost estimates. 0.0 = free tier.
    price_in_per_m: float = 0.0
    price_out_per_m: float = 0.0

    def probes(self) -> list[str]:
        return self.probe_models or self.models


PROVIDERS: dict[str, ProviderConfig] = {
    "groq": ProviderConfig(
        label="Groq (free tier — primary)",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        default_model="openai/gpt-oss-120b",
        models=["openai/gpt-oss-120b", "llama-3.3-70b-versatile"],
        probe_models=[
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
        ],
    ),
    # Same service, different organisation. Groq meters tokens-per-day per ORG, so a second
    # account is a genuine second allowance rather than a duplicate. Placed first in the chain
    # because it is the same speed and the same models — falling through to a slower provider
    # should be the last resort, not the first.
    "groq2": ProviderConfig(
        label="Groq (second organisation)",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY_2",
        default_model="openai/gpt-oss-120b",
        models=["openai/gpt-oss-120b", "llama-3.3-70b-versatile"],
    ),
    "groq3": ProviderConfig(
        label="Groq (third organisation)",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY_3",
        default_model="openai/gpt-oss-120b",
        models=["openai/gpt-oss-120b", "llama-3.3-70b-versatile"],
    ),
    "google": ProviderConfig(
        label="Google AI Studio (free tier)",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        api_key_env="GOOGLE_API_KEY",
        default_model="gemini-3.5-flash",
        # The free-tier quota is per *day*, per *project*, per *model* — so each entry here has
        # its own independent allowance and exhausting one does not touch the others. That makes
        # the in-provider chain genuinely useful rather than decorative.
        #
        # `gemini-2.0-flash` was in this list and is deliberately not any more: it was the first
        # model to run dry on the fellowship account, and a chain that leads with an exhausted
        # model just adds a round trip before failing over.
        models=["gemini-3.5-flash", "gemini-3.6-flash", "gemini-flash-latest"],
    ),
    "openrouter": ProviderConfig(
        label="OpenRouter (free — fallback only, 50 req/day)",
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        api_key_env="OPENROUTER_API_KEY",
        default_model="cohere/north-mini-code:free",
        models=["cohere/north-mini-code:free", "nvidia/nemotron-3-nano-30b-a3b:free"],
    ),
    "xai": ProviderConfig(
        label="xAI Grok",
        base_url="https://api.x.ai/v1",
        api_key_env="XAI_API_KEY",
        default_model="grok-3-mini",
        models=["grok-3-mini", "grok-3"],
    ),
    "openai": ProviderConfig(
        label="OpenAI (paid)",
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        default_model="gpt-4o-mini",
        models=["gpt-4o-mini", "gpt-4o"],
        price_in_per_m=0.15,
        price_out_per_m=0.60,
    ),
}

# Every registered backend except the primary, in preference order. This is the *default* for
# LLM_FALLBACK_PROVIDERS, so adding a key to the environment or to deployment secrets widens
# failover with no other configuration. Unconfigured names are filtered out by provider_chain().
DEFAULT_FALLBACK_CHAIN = "groq2,groq3,google,openrouter,xai,openai"

# Models a user may pick per workspace, surfaced in the assistant configuration screen and in
# the multi-model advanced feature. Keyed by the id sent to the provider.
SELECTABLE_MODELS: dict[str, str] = {
    "openai/gpt-oss-120b": "GPT-OSS 120B — strongest reasoning",
    "llama-3.3-70b-versatile": "Llama 3.3 70B — fastest",
    "gemini-3.5-flash": "Gemini 3.5 Flash — long context",
}


class Settings(BaseModel):
    """Typed, validated view over the environment."""

    # --- LLM ---
    provider: str = Field(default_factory=lambda: os.getenv("LLM_PROVIDER", "groq"))
    model_override: str | None = Field(default_factory=lambda: os.getenv("LLM_MODEL") or None)
    temperature: float = Field(default_factory=lambda: _float("LLM_TEMPERATURE", 0.3))
    max_tokens: int = Field(default_factory=lambda: _int("LLM_MAX_TOKENS", 2048))
    fallback_providers: list[str] = Field(
        default_factory=lambda: _csv("LLM_FALLBACK_PROVIDERS", DEFAULT_FALLBACK_CHAIN))
    max_retries_per_call: int = 2
    rate_limit_backoff_seconds: float = Field(
        default_factory=lambda: _float("RATE_LIMIT_BACKOFF_SECONDS", 6.0))
    max_rate_limit_wait_seconds: float = Field(
        default_factory=lambda: _float("MAX_RATE_LIMIT_WAIT_SECONDS", 45.0))
    rate_limit_passes: int = Field(default_factory=lambda: _int("RATE_LIMIT_PASSES", 3))
    # Per-call ceiling. A chat turn that has not started producing tokens within this window is
    # a stall, not slow generation, and the user is better served by an error than by a spinner.
    agent_timeout_seconds: int = Field(default_factory=lambda: _int("AGENT_TIMEOUT_SECONDS", 60))
    # Minimum gap between model calls, process-wide. 0 disables pacing. Week 4 used this for long
    # unattended runs on a tokens-per-minute tier; here it stays available for the Phase 8
    # evaluation harness, which fires many calls back to back.
    min_call_interval_seconds: float = Field(
        default_factory=lambda: _float("MIN_CALL_INTERVAL_SECONDS", 0.0))

    # --- Budget ceilings, read by services.usage.UsageTracker ---
    # Interactive chat does not attach a tracker, so these bind only where one is passed in:
    # the evaluation and experiment runners, which are the parts that can run away unattended.
    max_agent_calls_per_run: int = Field(
        default_factory=lambda: _int("MAX_AGENT_CALLS_PER_RUN", 200))
    max_run_seconds: int = Field(default_factory=lambda: _int("MAX_RUN_SECONDS", 1800))
    max_cost_usd_per_run: float = Field(
        default_factory=lambda: _float("MAX_COST_USD_PER_RUN", 0.50))

    # --- Database ---
    database_url: str = Field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./workspace.db"))

    # --- Authentication ---
    jwt_secret: str = Field(default_factory=lambda: os.getenv("JWT_SECRET", ""))
    jwt_algorithm: str = Field(default_factory=lambda: os.getenv("JWT_ALGORITHM", "HS256"))
    jwt_expire_minutes: int = Field(default_factory=lambda: _int("JWT_EXPIRE_MINUTES", 1440))

    # --- Embeddings, chunking, retrieval ---
    embedding_provider: str = Field(
        default_factory=lambda: os.getenv("EMBEDDING_PROVIDER", "google"))
    embedding_model: str = Field(
        default_factory=lambda: os.getenv("EMBEDDING_MODEL", "gemini-embedding-001"))
    embedding_dim: int = Field(default_factory=lambda: _int("EMBEDDING_DIM", 768))
    chunk_size: int = Field(default_factory=lambda: _int("CHUNK_SIZE", 800))
    chunk_overlap: int = Field(default_factory=lambda: _int("CHUNK_OVERLAP", 120))
    retrieval_mode: str = Field(default_factory=lambda: os.getenv("RETRIEVAL_MODE", "hybrid"))
    retrieval_top_k: int = Field(default_factory=lambda: _int("RETRIEVAL_TOP_K", 6))

    # --- Long-term memory ---
    memory_enabled: bool = Field(default_factory=lambda: _bool("MEMORY_ENABLED", True))
    memory_max_items_in_context: int = Field(
        default_factory=lambda: _int("MEMORY_MAX_ITEMS_IN_CONTEXT", 8))
    memory_min_importance: float = Field(
        default_factory=lambda: _float("MEMORY_MIN_IMPORTANCE", 0.3))

    # --- API ---
    cors_origins: list[str] = Field(
        default_factory=lambda: _csv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"))
    max_upload_mb: int = Field(default_factory=lambda: _int("MAX_UPLOAD_MB", 20))
    rate_limit_per_minute: int = Field(default_factory=lambda: _int("RATE_LIMIT_PER_MINUTE", 30))
    api_host: str = Field(default_factory=lambda: os.getenv("API_HOST", "127.0.0.1"))
    api_port: int = Field(default_factory=lambda: _int("API_PORT", 8000))

    # --- Paths ---
    upload_dir: Path = ROOT / "data" / "uploads"

    # ------------------------------------------------------------------ helpers
    def provider_config(self, name: str | None = None) -> ProviderConfig:
        key = name or self.provider
        if key not in PROVIDERS:
            raise ValueError(f"Unknown provider {key!r}. Choose one of {list(PROVIDERS)}.")
        return PROVIDERS[key]

    def active_model(self) -> str:
        """Model to use when a workspace has not chosen one: override wins, else provider default."""
        return self.model_override or self.provider_config().default_model

    def provider_chain(self) -> list[str]:
        """Active provider first, then configured fallbacks that actually have a key set."""
        chain = [self.provider]
        for name in self.fallback_providers:
            if name in PROVIDERS and name not in chain and os.getenv(PROVIDERS[name].api_key_env):
                chain.append(name)
        return chain

    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def db_configured(self) -> bool:
        url = self.database_url or ""
        return bool(url) and "<password>" not in url.lower() and "<project-ref>" not in url


# Import this singleton everywhere.
settings = Settings()
