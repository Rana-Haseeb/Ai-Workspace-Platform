"""Long-term memory items."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MemoryKind = Literal["preference", "fact", "topic", "pinned"]


class MemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: MemoryKind
    content: str
    importance: float
    is_pinned: bool
    workspace_id: int | None
    use_count: int
    last_used_at: datetime | None
    created_at: datetime
    # Computed, not stored: the importance x recency figure that decides injection order.
    # Exposed so the UI can show *why* one memory outranks another rather than just listing them.
    rank_score: float = 0.0
    in_context: bool = False


class MemoryCreate(BaseModel):
    content: str = Field(min_length=3, max_length=2000)
    kind: MemoryKind = "fact"
    importance: float = Field(default=0.6, ge=0.0, le=1.0)
    # None means the memory follows the user into every workspace.
    workspace_scoped: bool = True


class MemoryUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=3, max_length=2000)
    kind: MemoryKind | None = None
    importance: float | None = Field(default=None, ge=0.0, le=1.0)
    is_pinned: bool | None = None


class MemoryStatus(BaseModel):
    """A summary of what the assistant currently remembers."""

    total: int
    pinned: int
    in_context: int
    by_kind: dict[str, int]
    enabled: bool
    max_in_context: int
