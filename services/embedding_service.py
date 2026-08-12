"""Turning text into vectors.

**Why raw HTTP and not a client library.** The Google embedding endpoint needs two parameters
that matter here and that the OpenAI-compatible shim does not expose: ``outputDimensionality``
and ``taskType``. Both are load-bearing, so this talks to the native endpoint directly.

**Why 768 dimensions when the model is natively 3072.** ``gemini-embedding-001`` is trained so
that a truncated prefix of the vector is still a usable embedding. 768 stores four times smaller
— which matters when the vector lives in a JSON column — and measurably still separates
relevant from irrelevant text (0.77 versus 0.46 cosine on a probe question).

**Why taskType at all.** The same sentence is embedded differently depending on whether it is a
question or a passage being searched. Asymmetric embedding is free accuracy, and skipping it is
the most common reason a working RAG pipeline retrieves badly.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from core.config import settings
from core.logging import get_logger

log = get_logger("embeddings")

GOOGLE_BASE = "https://generativelanguage.googleapis.com/v1beta"

# The API rejects oversized batches; chunks are ~800 characters so this stays well inside limits.
BATCH_SIZE = 20
MAX_RETRIES = 5
# Ceiling on any single wait. A per-minute bucket refills within this; anything longer is a
# daily quota, which no amount of waiting inside one request will fix.
MAX_BACKOFF_SECONDS = 70.0
# A short pause between batches. Ingesting a 129-page PDF is 8 batches fired back to back, which
# is what exhausted the per-minute allowance in the first place. Pacing costs a second and
# avoids the stall entirely.
INTER_BATCH_PAUSE = 1.0


class EmbeddingError(RuntimeError):
    """Raised when text could not be embedded."""


def is_configured() -> bool:
    """Whether a real embedding backend is available."""
    if settings.embedding_provider == "none":
        return False
    if settings.embedding_provider == "google":
        return bool(os.getenv("GOOGLE_API_KEY"))
    if settings.embedding_provider == "openai":
        return bool(os.getenv("OPENAI_API_KEY"))
    return False


def describe() -> str:
    if not is_configured():
        return "none (keyword search only)"
    return f"{settings.embedding_provider}:{settings.embedding_model} at {settings.embedding_dim}d"


def _post(url: str, payload: dict, timeout: int = 60) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def _google_batch(texts: list[str], task_type: str) -> list[list[float]]:
    key = os.getenv("GOOGLE_API_KEY", "")
    if not key:
        raise EmbeddingError("GOOGLE_API_KEY is not set.")

    model = settings.embedding_model
    url = f"{GOOGLE_BASE}/models/{model}:batchEmbedContents?key={key}"
    payload = {
        "requests": [
            {
                "model": f"models/{model}",
                "content": {"parts": [{"text": text}]},
                "taskType": task_type,
                "outputDimensionality": settings.embedding_dim,
            }
            for text in texts
        ]
    }

    last: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            body = _post(url, payload)
            return [item["values"] for item in body["embeddings"]]
        except urllib.error.HTTPError as error:
            raw = error.read().decode()
            last = EmbeddingError(f"HTTP {error.code}: {raw[:200]}")
            # 429 and 5xx are worth waiting out; a 400 is a bad request and will not improve.
            if error.code not in {429, 500, 502, 503, 504}:
                raise last from error
            # A *daily* quota is not worth waiting out. Google returns `retryDelay: 58s` even
            # when the exhausted quota is per-day, so honouring it blindly means five retries
            # over four minutes for something that resets tomorrow. Measured in Phase 9: this
            # turned an instant, honest degradation to keyword-only search into a four-minute
            # stall, and hung the test suite for the same reason.
            if _is_daily_quota(raw):
                log.warning("Daily embedding quota exhausted; not retrying. %s", _quota_id(raw))
                raise last from error
            if attempt == MAX_RETRIES - 1:
                break
            wait = _retry_after(raw, attempt)
            log.warning(
                "Embedding backend returned %s, waiting %.0fs (attempt %d/%d)",
                error.code, wait, attempt + 1, MAX_RETRIES,
            )
            time.sleep(wait)
        except Exception as error:  # noqa: BLE001
            last = EmbeddingError(str(error)[:200])
            if attempt == MAX_RETRIES - 1:
                break
            time.sleep(min(2 ** attempt, MAX_BACKOFF_SECONDS))

    raise last or EmbeddingError("Embedding failed for an unknown reason.")


def _quota_id(error_body: str) -> str:
    """The name of the exhausted quota, e.g. ``EmbedContentRequestsPerDayPerProjectPerModel``."""
    try:
        for detail in json.loads(error_body)["error"].get("details", []):
            if "QuotaFailure" in detail.get("@type", ""):
                violations = detail.get("violations", [])
                if violations:
                    return str(violations[0].get("quotaId", ""))
    except Exception:  # noqa: BLE001 — a malformed body just means we cannot tell
        pass
    return ""


def _is_daily_quota(error_body: str) -> bool:
    """Whether the exhausted quota resets daily rather than per minute.

    Conservative: if the quota cannot be identified, this returns False and the normal retry
    path runs. Guessing "daily" wrongly would turn a recoverable blip into a hard failure.
    """
    return "PerDay" in _quota_id(error_body)


def _retry_after(error_body: str, attempt: int) -> float:
    """How long to wait, preferring the delay the API itself asked for.

    Google returns a ``RetryInfo`` block with a ``retryDelay`` like ``"37s"``. Honouring it beats
    guessing: the earlier exponential backoff topped out at 4 seconds against a *per-minute*
    quota, so every retry failed for the same reason the first attempt did.
    """
    try:
        details = json.loads(error_body)["error"].get("details", [])
        for detail in details:
            if "RetryInfo" in detail.get("@type", "") and detail.get("retryDelay"):
                seconds = float(str(detail["retryDelay"]).rstrip("s"))
                return min(max(seconds + 1.0, 1.0), MAX_BACKOFF_SECONDS)
    except Exception:  # noqa: BLE001 — a malformed error body just means we fall back
        pass
    # No stated delay: back off geometrically, but far enough to outlast a per-minute window.
    return min(5.0 * (2 ** attempt), MAX_BACKOFF_SECONDS)


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed passages for storage. Batched, because one request per chunk is needlessly slow."""
    if not texts:
        return []
    if not is_configured():
        raise EmbeddingError(
            "No embedding provider is configured. Set EMBEDDING_PROVIDER and its key, or the "
            "knowledge base falls back to keyword search."
        )

    vectors: list[list[float]] = []
    started = time.perf_counter()
    batches = range(0, len(texts), BATCH_SIZE)
    for position, index in enumerate(batches):
        if position:
            time.sleep(INTER_BATCH_PAUSE)
        batch = texts[index : index + BATCH_SIZE]
        vectors.extend(_google_batch(batch, "RETRIEVAL_DOCUMENT"))

    log.info(
        "Embedded %d chunks in %.2fs (%s)", len(texts), time.perf_counter() - started, describe()
    )
    return vectors


def embed_query(text: str) -> list[float]:
    """Embed a question. Uses the query task type, which is not the document one."""
    if not is_configured():
        raise EmbeddingError("No embedding provider is configured.")
    return _google_batch([text], "RETRIEVAL_QUERY")[0]
