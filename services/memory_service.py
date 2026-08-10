"""Long-term memory: what the assistant knows about *you*, not about your documents.

This module is the answer to the question "how is memory different from RAG?", so it is worth
being precise about the difference rather than leaving it implied.

|              | Knowledge base (Phase 4)          | Memory (here)                        |
|--------------|-----------------------------------|--------------------------------------|
| Holds        | fragments of a document           | facts about the user                 |
| Created by   | uploading a file                  | a model reading the conversation     |
| Retrieved by | similarity to the current question| importance x recency, always         |
| Lifetime     | immutable until deleted           | updated as the person changes        |
| Scope        | one workspace                     | the user, optionally one workspace   |

The retrieval difference is the substantive one. A document chunk is fetched *because you asked
about it*. A memory is injected **whether or not the question mentions it** — that is what makes
"given what I told you last week" work when the current message never says what that was.

Ranking is ``importance x recency``, not similarity, for the same reason: "I prefer concise
answers" has to apply to a question about Postgres, and no similarity function will connect
those two sentences.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import settings
from core.logging import get_logger
from db.models import AssistantSettings, Log, MemoryItem, Workspace

log = get_logger("memory")

# Kinds a memory can be. Deliberately few — a taxonomy nobody can keep straight becomes noise.
KINDS = ("preference", "fact", "topic", "pinned")

# Half-life for the recency term, in days. After this long a memory carries half the weight it
# started with. Two weeks is chosen so a preference stated at the start of a project still
# outranks a passing remark from yesterday, without anything ever fully disappearing.
RECENCY_HALF_LIFE_DAYS = 14.0

# Messages shorter than this rarely contain a durable fact ("ok", "thanks", "yes"), and paying
# for an extraction call on them is pure waste.
MIN_CHARS_FOR_EXTRACTION = 25

# How many existing memories are shown to the extractor so it can avoid repeating them.
DEDUP_CONTEXT_LIMIT = 40


class ExtractedMemory(BaseModel):
    kind: str = Field(description="One of: preference, fact, topic")
    content: str = Field(description="The fact, written as a standalone sentence in the third person")
    importance: float = Field(description="0.0 to 1.0. How much this should influence future answers")


class ExtractionResult(BaseModel):
    memories: list[ExtractedMemory] = Field(default_factory=list)


EXTRACTION_SYSTEM = """You maintain a long-term memory about a user, from their messages to an assistant.

Record only things that will still be true and useful *next week*:
- stated preferences about how they want to be helped
- durable facts about their work, tools, constraints or situation
- topics they return to repeatedly

Do not record:
- anything already in the existing memories below, or a rephrasing of it
- the content of their current question, or your answer to it
- one-off requests, pleasantries, or anything that stops being true once this task ends

Write each memory as a standalone sentence in the third person, understandable with no other
context. "Prefers concise answers" — not "they said they want it short".

Set importance from 0.0 to 1.0: a core working preference is 0.8, a passing detail is 0.2.

Return an empty list when the message contains nothing durable. That is the common case, and an
empty list is a better answer than a weak memory."""


# --------------------------------------------------------------------- retrieval
def _recency_weight(created_at: datetime, now: datetime) -> float:
    """Exponential decay by age. 1.0 today, 0.5 after one half-life, never quite zero."""
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age_days = max((now - created_at).total_seconds() / 86400.0, 0.0)
    return math.pow(0.5, age_days / RECENCY_HALF_LIFE_DAYS)


def rank_score(item: MemoryItem, now: datetime) -> float:
    """How strongly this memory should be injected. Pinned items are placed beyond competition."""
    if item.is_pinned:
        return float("inf")
    return item.importance * _recency_weight(item.created_at, now)


def candidates(db: Session, user_id: int, workspace_id: int | None) -> list[MemoryItem]:
    """Memories that apply here: this workspace's, plus the user's global ones.

    A memory with ``workspace_id`` NULL follows the person everywhere — "prefers concise answers"
    should not have to be re-learned in every workspace. One scoped to a workspace stays there,
    because "this project uses Postgres 16" is wrong advice in a different project.
    """
    return list(
        db.execute(
            select(MemoryItem).where(
                MemoryItem.user_id == user_id,
                (MemoryItem.workspace_id == workspace_id) | (MemoryItem.workspace_id.is_(None)),
            )
        ).scalars()
    )


def retrieve(
    db: Session, user_id: int, workspace_id: int | None, limit: int | None = None
) -> list[MemoryItem]:
    """The memories to inject into the next prompt, best first.

    Note what is *not* an argument: the user's question. Memory retrieval is deliberately
    question-independent — see the module docstring.
    """
    limit = limit or settings.memory_max_items_in_context
    now = datetime.now(timezone.utc)

    items = [
        item for item in candidates(db, user_id, workspace_id)
        if item.is_pinned or item.importance >= settings.memory_min_importance
    ]
    items.sort(key=lambda item: rank_score(item, now), reverse=True)
    return items[:limit]


def mark_used(db: Session, items: list[MemoryItem]) -> None:
    """Record that these memories informed an answer.

    Usage is what tells a pruning pass later which memories earn their place, and it is what the
    dashboard's "most-used memories" reads.
    """
    now = datetime.now(timezone.utc)
    for item in items:
        item.use_count += 1
        item.last_used_at = now
    db.commit()


def context_block(items: list[MemoryItem]) -> str:
    """The memories formatted for the system prompt."""
    if not items:
        return ""
    lines = [f"- {item.content}" for item in items]
    return (
        "What you already know about this user, from previous conversations. Apply it without "
        "being asked, and without announcing that you are remembering:\n" + "\n".join(lines)
    )


# -------------------------------------------------------------------- extraction
def _existing_summary(db: Session, user_id: int, workspace_id: int | None) -> str:
    items = candidates(db, user_id, workspace_id)[:DEDUP_CONTEXT_LIMIT]
    if not items:
        return "(none yet)"
    return "\n".join(f"- {item.content}" for item in items)


def _is_duplicate(content: str, existing: list[MemoryItem]) -> bool:
    """Cheap near-duplicate guard behind the model's own de-duplication.

    The extractor is told not to repeat itself and mostly obeys, but "Prefers concise answers"
    and "Prefers concise answers." are one memory, and only a string check catches that reliably.
    """
    normalised = " ".join(content.lower().split()).rstrip(".")
    return any(" ".join(item.content.lower().split()).rstrip(".") == normalised for item in existing)


def extract_and_store(
    db: Session,
    user_id: int,
    workspace: Workspace,
    settings_row: AssistantSettings,
    user_message: str,
) -> list[MemoryItem]:
    """Read one user message for durable facts and store the new ones.

    Never raises. Memory is an enhancement; a failed extraction must not cost the user the
    conversation that produced it.
    """
    if not settings.memory_enabled or not settings_row.use_memory:
        return []
    if len(user_message.strip()) < MIN_CHARS_FOR_EXTRACTION:
        return []

    from services.chat_service import llm_for

    existing = candidates(db, user_id, workspace.id)

    try:
        result = llm_for(settings_row, agent_id="memory_extract").structured(
            system=EXTRACTION_SYSTEM,
            user=(
                f"Existing memories:\n{_existing_summary(db, user_id, workspace.id)}\n\n"
                f"New message from the user:\n{user_message[:4000]}"
            ),
            schema=ExtractionResult,
        )
    except Exception as error:  # noqa: BLE001
        log.warning("Memory extraction failed, continuing without it: %s", error)
        return []

    stored: list[MemoryItem] = []
    for extracted in result.memories:
        content = extracted.content.strip()
        if not content or _is_duplicate(content, existing):
            continue
        kind = extracted.kind.strip().lower()
        item = MemoryItem(
            user_id=user_id,
            # Preferences follow the person; facts and topics stay with the workspace they were
            # learned in, because a project-specific detail is wrong advice elsewhere.
            workspace_id=None if kind == "preference" else workspace.id,
            kind=kind if kind in KINDS else "fact",
            content=content[:2000],
            importance=min(max(float(extracted.importance), 0.0), 1.0),
        )
        db.add(item)
        stored.append(item)
        existing.append(item)

    if stored:
        db.add(Log(
            user_id=user_id, workspace_id=workspace.id, event="memory",
            detail=f"stored {len(stored)} memories", status="ok",
        ))
        db.commit()
        for item in stored:
            db.refresh(item)
        log.info("Stored %d new memories for user %s", len(stored), user_id)

    return stored
