"""Assistant configuration for a workspace — the eight fields the challenge requires.

Bounds live here rather than in the router or the UI, so the same rule is enforced whatever the
caller is, and appears automatically in the generated OpenAPI docs.

Temperature is capped at 2.0 because that is the ceiling the OpenAI-compatible endpoints accept;
sending 3.0 is a provider error, not a creative assistant. ``max_tokens`` is floored at 256
because a smaller ceiling truncates mid-sentence often enough to look like a bug.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Personality = Literal["professional", "friendly", "concise", "socratic", "enthusiastic"]
ResponseStyle = Literal["balanced", "detailed", "brief", "bullets", "technical"]


class AssistantSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assistant_name: str
    role: str
    system_prompt: str
    model: str | None
    temperature: float
    max_tokens: int
    personality: Personality
    response_style: ResponseStyle
    use_memory: bool
    use_knowledge_base: bool


class AssistantSettingsUpdate(BaseModel):
    """Every field optional, so the client can send only what changed."""

    assistant_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: str | None = Field(default=None, min_length=1, max_length=200)
    system_prompt: str | None = Field(default=None, min_length=1, max_length=8000)
    # None is meaningful here: it means "use the deployment default". Because None is also the
    # "field omitted" marker, the router uses `exclude_unset` to tell the two apart.
    model: str | None = Field(default=None, max_length=120)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=256, le=8192)
    personality: Personality | None = None
    response_style: ResponseStyle | None = None
    use_memory: bool | None = None
    use_knowledge_base: bool | None = None


class ModelOption(BaseModel):
    """One selectable model, for the picker in the settings screen."""

    id: str
    label: str
