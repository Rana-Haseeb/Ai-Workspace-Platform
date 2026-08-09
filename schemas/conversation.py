"""Conversations and messages."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: Literal["user", "assistant", "system"]
    content: str
    citations: list = Field(default_factory=list)
    memory_used: list = Field(default_factory=list)
    is_pinned: bool
    model: str | None
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    created_at: datetime


class ConversationResponse(BaseModel):
    """A conversation in a list: enough to render a row, not the whole transcript."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    session_id: str
    is_pinned: bool
    tags: list = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    preview: str = ""


class ConversationDetail(ConversationResponse):
    messages: list[MessageResponse] = Field(default_factory=list)


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    is_pinned: bool | None = None
    tags: list[str] | None = None


class ChatRequest(BaseModel):
    """One user turn."""

    content: str = Field(min_length=1, max_length=32000)


class ChatResponse(BaseModel):
    """The non-streaming reply, used by tests, scripts and the evaluation harness."""

    user_message: MessageResponse
    assistant_message: MessageResponse
    conversation_id: int
    title: str
