"""Turning a workspace's configuration and history into a model call, and persisting the result.

Two things live here that are easy to get wrong elsewhere.

**The system prompt is assembled, not stored.** The workspace holds a base prompt; personality
and response style are separate fields. Concatenating them at call time rather than at save time
means changing "response style" updates every future turn without rewriting anything, and the
stored prompt stays the thing the user actually typed.

**History is trimmed by turns, not tokens.** A token-exact window would need a tokenizer per
provider and would still be an estimate. A fixed number of recent turns is predictable, cheap,
and easy to explain — and Phase 8's conversation-length experiment measures what it costs.
"""
from __future__ import annotations

import time
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from core.logging import get_logger
from db.models import AssistantSettings, Conversation, Log, Message, Workspace
from services.llm_service import get_llm

log = get_logger("chat")

# How many previous messages are replayed to the model. 20 is ten exchanges — enough for
# "summarise what we decided" to work, short enough to stay well inside every model's context.
HISTORY_LIMIT = 20

# Title generation reads only the opening message; a longer prompt would cost more for no gain.
TITLE_MAX_CHARS = 400

PERSONALITY_INSTRUCTIONS = {
    "professional": "Write plainly and precisely. No filler, no enthusiasm you do not have.",
    "friendly": "Write warmly and conversationally, as a knowledgeable colleague would.",
    "concise": "Answer in as few words as the question honestly allows.",
    "socratic": "Lead with a question that exposes the crux before you answer it.",
    "enthusiastic": "Write with energy and momentum, without overstating what you know.",
}

STYLE_INSTRUCTIONS = {
    "balanced": "Match the length of the answer to the complexity of the question.",
    "detailed": "Give full reasoning and worked examples.",
    "brief": "Two or three sentences unless more is genuinely required.",
    "bullets": "Structure the answer as short bullet points.",
    "technical": "Assume an engineering audience. Use precise terms and include code where useful.",
}


DEFAULT_SYSTEM_PROMPT = "You are a helpful, precise assistant."


def build_system_prompt(settings_row: AssistantSettings) -> str:
    """Assemble the instruction block sent before every turn in this workspace.

    Every field is read through a fallback because SQLAlchemy column defaults are applied on
    INSERT, not on construction — an ``AssistantSettings()`` that has not been saved has ``None``
    everywhere. That makes this function safe to call on an unsaved object, which is what lets
    prompt assembly be unit tested without a database.
    """
    parts = [(settings_row.system_prompt or DEFAULT_SYSTEM_PROMPT).strip()]

    role = (settings_row.role or "").strip()
    if role:
        parts.append(f"Your role: {role}")

    personality = PERSONALITY_INSTRUCTIONS.get(settings_row.personality or "")
    if personality:
        parts.append(personality)

    style = STYLE_INSTRUCTIONS.get(settings_row.response_style or "")
    if style:
        parts.append(style)

    return "\n\n".join(part for part in parts if part)


def build_messages(
    settings_row: AssistantSettings, history: list[Message], user_content: str
) -> list[tuple[str, str]]:
    """The full ``(role, content)`` list for one turn: system prompt, recent history, new message."""
    messages: list[tuple[str, str]] = [("system", build_system_prompt(settings_row))]
    for message in history[-HISTORY_LIMIT:]:
        if message.role in {"user", "assistant"}:
            messages.append((message.role, message.content))
    messages.append(("user", user_content))
    return messages


def llm_for(settings_row: AssistantSettings, agent_id: str = "chat"):
    """An LLM client configured from this workspace's settings."""
    return get_llm(
        agent_id=agent_id,
        preferred_model=settings_row.model,
        temperature=settings_row.temperature,
        max_tokens=settings_row.max_tokens,
    )


# ---------------------------------------------------------------- conversations
def new_session_id() -> str:
    return uuid.uuid4().hex


def get_or_create_conversation(
    db: Session, workspace: Workspace, conversation_id: int | None
) -> Conversation:
    """Fetch a conversation in this workspace, or start one.

    The workspace is already ownership-checked by the caller's dependency. Filtering on
    ``workspace_id`` as well means a conversation id from *another* workspace cannot be smuggled
    in through a body parameter.
    """
    if conversation_id is not None:
        conversation = db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.workspace_id == workspace.id,
            )
        ).scalar_one_or_none()
        if conversation is not None:
            return conversation

    conversation = Conversation(
        workspace_id=workspace.id,
        title="New conversation",
        session_id=new_session_id(),
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def list_conversations(
    db: Session, workspace_id: int, query: str | None = None
) -> list[Conversation]:
    """Conversations in a workspace, pinned first, newest first.

    ``query`` matches the title *or* any message body, so searching for a phrase you remember
    saying finds the conversation even when the title never mentioned it. ``ilike`` on SQLite is
    case-insensitive for ASCII, and Postgres honours it natively; a shared index-backed
    full-text search is the Phase 9 performance note.
    """
    statement = select(Conversation).where(Conversation.workspace_id == workspace_id)

    if query and query.strip():
        pattern = f"%{query.strip()}%"
        matching_ids = select(Message.conversation_id).where(Message.content.ilike(pattern))
        statement = statement.where(
            or_(Conversation.title.ilike(pattern), Conversation.id.in_(matching_ids))
        )

    statement = statement.order_by(
        Conversation.is_pinned.desc(), Conversation.updated_at.desc()
    )
    return list(db.execute(statement).scalars())


def conversation_stats(db: Session, conversation_ids: list[int]) -> dict[int, tuple[int, str]]:
    """``{conversation_id: (message_count, preview)}`` for a list of conversations.

    One grouped query plus one preview query, rather than two queries per row. With twenty
    conversations in a sidebar the difference between 2 and 40 round trips is the difference
    between a list that appears and a list that arrives.
    """
    if not conversation_ids:
        return {}

    counts = dict(
        db.execute(
            select(Message.conversation_id, func.count(Message.id))
            .where(Message.conversation_id.in_(conversation_ids))
            .group_by(Message.conversation_id)
        ).all()
    )

    previews: dict[int, str] = {}
    rows = db.execute(
        select(Message.conversation_id, Message.content, Message.created_at)
        .where(Message.conversation_id.in_(conversation_ids), Message.role == "user")
        .order_by(Message.conversation_id, Message.created_at.desc())
    ).all()
    for conversation_id, content, _ in rows:
        previews.setdefault(conversation_id, content[:120])

    return {
        cid: (counts.get(cid, 0), previews.get(cid, "")) for cid in conversation_ids
    }


def history_for(db: Session, conversation_id: int) -> list[Message]:
    return list(
        db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at, Message.id)
        ).scalars()
    )


# --------------------------------------------------------------------- titling
def generate_title(settings_row: AssistantSettings, first_message: str) -> str:
    """A short title derived from the opening message.

    Falls back to a truncation of the message itself if the model call fails. A conversation
    that exists with a clumsy title is strictly better than a request that failed over naming.
    """
    fallback = first_message.strip().split("\n")[0][:60] or "New conversation"
    try:
        title = llm_for(settings_row, agent_id="title").complete(
            system=(
                "Write a title of at most six words for a conversation that opens with the "
                "message below. Reply with the title only — no quotes, no punctuation at the "
                "end, no preamble."
            ),
            user=first_message[:TITLE_MAX_CHARS],
        )
        cleaned = title.strip().strip('"').strip("'").split("\n")[0][:200]
        return cleaned or fallback
    except Exception as exc:  # noqa: BLE001
        log.warning("Title generation failed, falling back to the message: %s", exc)
        return fallback


# -------------------------------------------------------------- persisting turns
def record_user_message(db: Session, conversation: Conversation, content: str) -> Message:
    message = Message(conversation_id=conversation.id, role="user", content=content)
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def record_assistant_message(
    db: Session,
    conversation: Conversation,
    content: str,
    *,
    model: str | None,
    provider: str | None,
    tokens_in: int,
    tokens_out: int,
    latency_ms: int,
    user_id: int,
) -> Message:
    """Persist the reply and log the call.

    Both happen together on purpose: the dashboard reads ``logs`` and the transcript reads
    ``messages``, and a reply that appears in one but not the other makes the usage numbers a
    lie.
    """
    message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=content,
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency_ms,
    )
    db.add(message)

    db.add(
        Log(
            user_id=user_id,
            workspace_id=conversation.workspace_id,
            event="chat",
            provider=provider,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            status="ok",
        )
    )

    # Touching the conversation is what moves it to the top of the sidebar.
    conversation.updated_at = func.now()
    db.commit()
    db.refresh(message)
    return message


def complete_turn(
    db: Session, workspace: Workspace, conversation: Conversation, user_content: str, user_id: int
) -> tuple[Message, Message]:
    """One full non-streaming exchange. Used by tests, scripts and the evaluation harness."""
    settings_row = workspace.settings
    history = history_for(db, conversation.id)
    is_first = len(history) == 0

    user_message = record_user_message(db, conversation, user_content)

    client = llm_for(settings_row)
    started = time.perf_counter()
    reply = client.chat(build_messages(settings_row, history, user_content))
    latency_ms = int((time.perf_counter() - started) * 1000)

    assistant_message = record_assistant_message(
        db,
        conversation,
        reply,
        model=client.last_used_model,
        provider=client.last_used_provider,
        tokens_in=sum(len(c) for _, c in build_messages(settings_row, history, user_content)) // 4,
        tokens_out=len(reply) // 4,
        latency_ms=latency_ms,
        user_id=user_id,
    )

    if is_first:
        conversation.title = generate_title(settings_row, user_content)
        db.commit()

    return user_message, assistant_message
