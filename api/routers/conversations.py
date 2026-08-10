"""Conversations and chat.

Routes are nested under ``/api/workspaces/{workspace_id}`` so every one of them resolves through
``OwnedWorkspace`` and inherits the ownership check. A conversation id belonging to a different
workspace cannot be reached even with a valid token, because the lookup filters on both ids.

Two ways to send a message:

* ``POST .../messages`` returns the finished reply as JSON. Tests, scripts and the evaluation
  harness use this — a single deterministic response is far easier to assert on.
* ``POST .../stream`` returns newline-delimited JSON events as the reply generates. The browser
  uses this.

NDJSON rather than Server-Sent Events: SSE's ``text/event-stream`` framing adds ``data:``
prefixes and blank-line terminators to parse around, and its automatic reconnection is actively
unwanted here — a dropped chat stream should surface, not silently replay.
"""
from __future__ import annotations

import json
import time

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from api.deps import CurrentUser, DbSession, OwnedWorkspace
from core.logging import get_logger
from db.base import SessionLocal
from db.models import Conversation, Log, Message
from schemas.conversation import (
    ChatRequest,
    ChatResponse,
    ConversationCreate,
    ConversationDetail,
    ConversationResponse,
    ConversationUpdate,
    MessageResponse,
)
from services import chat_service
from services.llm_service import LLMError

log = get_logger("conversations")

router = APIRouter(prefix="/api/workspaces/{workspace_id}/conversations", tags=["conversations"])


def _row(conversation: Conversation, count: int = 0, preview: str = "") -> ConversationResponse:
    response = ConversationResponse.model_validate(conversation)
    response.message_count = count
    response.preview = preview
    return response


def _load(db, workspace_id: int, conversation_id: int) -> Conversation:
    conversation = db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.workspace_id == workspace_id
        )
    ).scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conversation


# ------------------------------------------------------------------------ list
@router.get("", response_model=list[ConversationResponse])
def list_conversations(
    workspace: OwnedWorkspace,
    db: DbSession,
    q: str | None = Query(default=None, max_length=200, description="Search titles and message bodies"),
) -> list[ConversationResponse]:
    rows = chat_service.list_conversations(db, workspace.id, q)
    stats = chat_service.conversation_stats(db, [c.id for c in rows])
    return [_row(c, *stats.get(c.id, (0, ""))) for c in rows]


@router.post("", response_model=ConversationDetail, status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ConversationCreate, workspace: OwnedWorkspace, db: DbSession
) -> ConversationDetail:
    conversation = Conversation(
        workspace_id=workspace.id,
        title=payload.title or "New conversation",
        session_id=chat_service.new_session_id(),
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return ConversationDetail.model_validate(conversation)


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: int, workspace: OwnedWorkspace, db: DbSession
) -> ConversationDetail:
    conversation = _load(db, workspace.id, conversation_id)
    detail = ConversationDetail.model_validate(conversation)
    detail.messages = [
        MessageResponse.model_validate(m) for m in chat_service.history_for(db, conversation.id)
    ]
    detail.message_count = len(detail.messages)
    return detail


@router.patch("/{conversation_id}", response_model=ConversationResponse)
def update_conversation(
    conversation_id: int, payload: ConversationUpdate, workspace: OwnedWorkspace, db: DbSession
) -> ConversationResponse:
    conversation = _load(db, workspace.id, conversation_id)
    fields = payload.model_dump(exclude_unset=True)
    if "title" in fields and fields["title"]:
        conversation.title = fields["title"].strip()
    if "is_pinned" in fields and fields["is_pinned"] is not None:
        conversation.is_pinned = fields["is_pinned"]
    if "tags" in fields and fields["tags"] is not None:
        # De-duplicated, trimmed, capped. Tags are a browsing aid; an unbounded list from the
        # client is a storage problem wearing a feature's clothes.
        conversation.tags = sorted({t.strip()[:40] for t in fields["tags"] if t.strip()})[:12]
    db.commit()
    db.refresh(conversation)
    return _row(conversation)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: int, workspace: OwnedWorkspace, db: DbSession) -> None:
    db.delete(_load(db, workspace.id, conversation_id))
    db.commit()


# --------------------------------------------------------------- non-streaming
@router.post("/{conversation_id}/messages", response_model=ChatResponse)
def send_message(
    conversation_id: int,
    payload: ChatRequest,
    workspace: OwnedWorkspace,
    user: CurrentUser,
    db: DbSession,
) -> ChatResponse:
    conversation = _load(db, workspace.id, conversation_id)
    try:
        user_message, assistant_message = chat_service.complete_turn(
            db, workspace, conversation, payload.content, user.id
        )
    except LLMError as error:
        db.add(Log(user_id=user.id, workspace_id=workspace.id, event="chat",
                   detail=str(error), status="failed"))
        db.commit()
        # 502: the platform is fine, the upstream model is not. A 500 would suggest our bug.
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error))

    return ChatResponse(
        user_message=MessageResponse.model_validate(user_message),
        assistant_message=MessageResponse.model_validate(assistant_message),
        conversation_id=conversation.id,
        title=conversation.title,
    )


# ------------------------------------------------------------------- streaming
@router.post("/{conversation_id}/stream")
def stream_message(
    conversation_id: int,
    payload: ChatRequest,
    workspace: OwnedWorkspace,
    user: CurrentUser,
    db: DbSession,
) -> StreamingResponse:
    conversation = _load(db, workspace.id, conversation_id)
    settings_row = workspace.settings
    history = chat_service.history_for(db, conversation.id)
    is_first = len(history) == 0

    # Retrieval happens before the response starts, so the citations can be sent to the client
    # up front — the UI shows which sources are being consulted while the answer is still
    # generating, rather than revealing them at the end.
    retrieved = chat_service.retrieve_context(db, workspace, settings_row, payload.content)
    citations = [c.to_dict() for c in retrieved.citations]
    messages = chat_service.build_messages(
        settings_row, history, payload.content, retrieved.context_block()
    )

    user_message = chat_service.record_user_message(db, conversation, payload.content)
    user_message_id = user_message.id
    conversation_id_value = conversation.id
    workspace_id_value = workspace.id
    user_id_value = user.id

    def event_stream():
        # A session of its own. The request-scoped one is closed when this generator is still
        # producing, because the response has already started by then.
        session = SessionLocal()
        try:
            yield json.dumps({
                "type": "start",
                "conversation_id": conversation_id_value,
                "user_message_id": user_message_id,
                "citations": citations,
                "retrieval_mode": retrieved.mode,
            }) + "\n"

            client = chat_service.llm_for(settings_row)
            collected: list[str] = []
            started = time.perf_counter()

            try:
                for piece in client.stream_chat(messages):
                    collected.append(piece)
                    yield json.dumps({"type": "token", "text": piece}) + "\n"
            except LLMError as error:
                session.add(Log(user_id=user_id_value, workspace_id=workspace_id_value,
                                event="chat", detail=str(error), status="failed"))
                session.commit()
                yield json.dumps({"type": "error", "detail": str(error)}) + "\n"
                return

            reply = "".join(collected)
            latency_ms = int((time.perf_counter() - started) * 1000)

            conversation_row = session.get(Conversation, conversation_id_value)
            assistant_message = chat_service.record_assistant_message(
                session,
                conversation_row,
                reply,
                model=client.last_used_model,
                provider=client.last_used_provider,
                tokens_in=sum(len(c) for _, c in messages) // 4,
                tokens_out=len(reply) // 4,
                latency_ms=latency_ms,
                user_id=user_id_value,
                citations=citations,
            )

            title = conversation_row.title
            if is_first:
                title = chat_service.generate_title(settings_row, payload.content)
                conversation_row.title = title
                session.commit()

            yield json.dumps({
                "type": "done",
                "message_id": assistant_message.id,
                "title": title,
                "model": client.last_used_model,
                "latency_ms": latency_ms,
                "tokens_out": assistant_message.tokens_out,
            }) + "\n"
        finally:
            session.close()

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        # Without this, a reverse proxy may buffer the whole reply and deliver it at once,
        # which turns streaming back into waiting.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------- message edits
@router.patch("/{conversation_id}/messages/{message_id}/pin", response_model=MessageResponse)
def toggle_pin(
    conversation_id: int, message_id: int, workspace: OwnedWorkspace, db: DbSession
) -> MessageResponse:
    _load(db, workspace.id, conversation_id)
    message = db.execute(
        select(Message).where(Message.id == message_id, Message.conversation_id == conversation_id)
    ).scalar_one_or_none()
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    message.is_pinned = not message.is_pinned
    db.commit()
    db.refresh(message)
    return MessageResponse.model_validate(message)
