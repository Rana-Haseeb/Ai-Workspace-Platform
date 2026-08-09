"""Workspace request and response models.

Phase 1 needs only enough of this to prove isolation works. Phase 2 adds update, delete and the
assistant-settings payload.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    # A lucide-react icon name such as "flask" or "briefcase". Never an emoji.
    icon: str = Field(default="folder", max_length=40)


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    icon: str
    created_at: datetime
