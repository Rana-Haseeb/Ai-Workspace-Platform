"""What the workspace has actually done, counted from the database.

Every number here is a live aggregate over the tables that hold the thing being counted — there
is no counter column being incremented alongside the real data, because a denormalised total is
a number that can be wrong, and a dashboard whose figures disagree with the app is worse than no
dashboard.

The cost of that choice is a query per metric. At this scale each is an indexed COUNT over a few
thousand rows; the Phase 9 performance report measures it rather than assuming.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.config import PROVIDERS
from db.models import (
    Chunk,
    Conversation,
    Document,
    Log,
    MemoryItem,
    Message,
    PromptTemplate,
    Workspace,
)

# How far back the activity feed and the daily chart look.
ACTIVITY_DAYS = 14
RECENT_EVENTS = 12


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def estimate_cost(provider: str | None, tokens_in: int, tokens_out: int) -> float:
    """Cost in USD for one call, from the provider's published rates.

    Free tiers are priced at zero in the registry, so this returns 0.0 for Groq and Google — the
    honest figure, not a placeholder. Tokens are the number that actually varies, which is why
    the dashboard leads with them and treats cost as secondary.
    """
    config = PROVIDERS.get(provider or "")
    if config is None:
        return 0.0
    return (
        tokens_in / 1_000_000 * config.price_in_per_m
        + tokens_out / 1_000_000 * config.price_out_per_m
    )


def workspace_totals(db: Session, workspace: Workspace, user_id: int) -> dict:
    """The headline counts for one workspace."""
    conversations = db.execute(
        select(func.count(Conversation.id)).where(Conversation.workspace_id == workspace.id)
    ).scalar_one()

    messages = db.execute(
        select(func.count(Message.id))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Conversation.workspace_id == workspace.id)
    ).scalar_one()

    documents = db.execute(
        select(func.count(Document.id)).where(Document.workspace_id == workspace.id)
    ).scalar_one()

    chunks = db.execute(
        select(func.count(Chunk.id))
        .join(Document, Document.id == Chunk.document_id)
        .where(Document.workspace_id == workspace.id)
    ).scalar_one()

    # Memory and prompts are user-scoped: a null workspace_id means it applies everywhere, so
    # both the workspace's own and the user's global ones are counted here.
    memories = db.execute(
        select(func.count(MemoryItem.id)).where(
            MemoryItem.user_id == user_id,
            (MemoryItem.workspace_id == workspace.id) | (MemoryItem.workspace_id.is_(None)),
        )
    ).scalar_one()

    prompts = db.execute(
        select(func.count(PromptTemplate.id)).where(
            PromptTemplate.user_id == user_id,
            PromptTemplate.is_current.is_(True),
            (PromptTemplate.workspace_id == workspace.id)
            | (PromptTemplate.workspace_id.is_(None)),
        )
    ).scalar_one()

    return {
        "conversations": conversations,
        "messages": messages,
        "documents": documents,
        "chunks": chunks,
        "memories": memories,
        "prompts": prompts,
    }


# A log row counts as *work* if it consumed tokens or took measurable time. Administrative
# events — a workspace being created, a memory edited by hand, a login — are logged for the
# activity feed but are not model calls, and counting them would inflate "calls" with rows that
# never touched a provider.
def _is_work(column_tokens_in, column_tokens_out, column_latency):
    return (column_tokens_in > 0) | (column_tokens_out > 0) | (column_latency > 0)


def usage_totals(db: Session, workspace_id: int) -> dict:
    """Tokens, cost and latency for the calls that actually did work.

    ``logs`` rather than ``messages`` because not every billable call is a message: document
    embedding, memory extraction, title generation and skill runs all cost tokens, and a
    dashboard that counted only chat would understate usage by a wide margin.
    """
    rows = db.execute(
        select(Log.provider, Log.tokens_in, Log.tokens_out, Log.latency_ms, Log.status)
        .where(
            Log.workspace_id == workspace_id,
            _is_work(Log.tokens_in, Log.tokens_out, Log.latency_ms),
        )
    ).all()

    tokens_in = sum(row[1] or 0 for row in rows)
    tokens_out = sum(row[2] or 0 for row in rows)
    cost = sum(estimate_cost(row[0], row[1] or 0, row[2] or 0) for row in rows)

    timed = [row[3] for row in rows if row[3]]
    failed = sum(1 for row in rows if row[4] == "failed")

    return {
        "calls": len(rows),
        "failed_calls": failed,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "tokens_total": tokens_in + tokens_out,
        "estimated_cost_usd": round(cost, 4),
        "average_latency_ms": int(sum(timed) / len(timed)) if timed else 0,
        # p95, not the maximum: one 20-second cold start should not define "slow", but the
        # slowest 5% of requests is what users actually complain about.
        "p95_latency_ms": _percentile(timed, 95),
    }


def _percentile(values: list[int], percentile: int) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(int(len(ordered) * percentile / 100), len(ordered) - 1)
    return ordered[index]


def usage_by_event(db: Session, workspace_id: int) -> list[dict]:
    """Where the tokens went, broken down by what caused the call."""
    rows = db.execute(
        select(
            Log.event,
            func.count(Log.id),
            func.sum(Log.tokens_in),
            func.sum(Log.tokens_out),
        )
        .where(
            Log.workspace_id == workspace_id,
            _is_work(Log.tokens_in, Log.tokens_out, Log.latency_ms),
        )
        .group_by(Log.event)
        .order_by(func.count(Log.id).desc())
    ).all()

    return [
        {
            "event": event,
            "calls": calls,
            "tokens": (tokens_in or 0) + (tokens_out or 0),
        }
        for event, calls, tokens_in, tokens_out in rows
    ]


def daily_usage(db: Session, workspace_id: int, days: int = ACTIVITY_DAYS) -> list[dict]:
    """Tokens per day, with empty days included.

    Gaps are filled with zeros deliberately: a line chart that skips quiet days compresses time
    and makes a two-week pattern look like continuous activity.
    """
    since = _utcnow() - timedelta(days=days)
    rows = db.execute(
        select(Log.created_at, Log.tokens_in, Log.tokens_out)
        .where(Log.workspace_id == workspace_id, Log.created_at >= since)
    ).all()

    buckets: dict[str, int] = {}
    for created_at, tokens_in, tokens_out in rows:
        key = created_at.date().isoformat()
        buckets[key] = buckets.get(key, 0) + (tokens_in or 0) + (tokens_out or 0)

    today = _utcnow().date()
    return [
        {
            "date": (today - timedelta(days=offset)).isoformat(),
            "tokens": buckets.get((today - timedelta(days=offset)).isoformat(), 0),
        }
        for offset in range(days - 1, -1, -1)
    ]


def recent_activity(db: Session, workspace_id: int, limit: int = RECENT_EVENTS) -> list[dict]:
    rows = db.execute(
        select(Log)
        .where(Log.workspace_id == workspace_id)
        .order_by(Log.created_at.desc())
        .limit(limit)
    ).scalars().all()

    return [
        {
            "event": row.event,
            "detail": row.detail,
            "model": row.model,
            "tokens": (row.tokens_in or 0) + (row.tokens_out or 0),
            "latency_ms": row.latency_ms or 0,
            "status": row.status,
            "created_at": row.created_at,
        }
        for row in rows
    ]


def top_memories(db: Session, user_id: int, workspace_id: int, limit: int = 5) -> list[dict]:
    """The memories that have actually influenced answers, most-used first."""
    rows = db.execute(
        select(MemoryItem)
        .where(
            MemoryItem.user_id == user_id,
            (MemoryItem.workspace_id == workspace_id) | (MemoryItem.workspace_id.is_(None)),
            MemoryItem.use_count > 0,
        )
        .order_by(MemoryItem.use_count.desc())
        .limit(limit)
    ).scalars().all()

    return [{"content": row.content, "kind": row.kind, "use_count": row.use_count} for row in rows]
