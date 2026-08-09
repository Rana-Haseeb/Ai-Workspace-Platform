"""Workspace request and response models."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from schemas.settings import AssistantSettingsResponse

# Icons the picker offers. Names come from lucide-react, never emoji: emoji render differently
# on every platform and cannot take the theme's colour. Validated server-side so a crafted
# request cannot store a name the frontend will fail to render.
WORKSPACE_ICONS = [
    "folder", "flask", "briefcase", "graduation-cap", "code", "pen-tool",
    "chart-bar", "megaphone", "scale", "stethoscope", "rocket", "book-open",
]


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    icon: str = Field(default="folder", max_length=40)


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    icon: str | None = Field(default=None, max_length=40)


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    icon: str
    created_at: datetime


class WorkspaceDetail(WorkspaceResponse):
    """A workspace together with its assistant configuration.

    Returned as one payload because the settings screen needs both and a second round trip to
    fetch a guaranteed-to-exist 1:1 row would be waste.
    """

    settings: AssistantSettingsResponse
