"""Skills and prompt templates."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PromptCategory = Literal["writing", "programming", "research", "business", "education", "custom"]


# ---------------------------------------------------------------------- skills
class SkillSummary(BaseModel):
    """A skill as the picker renders it. Derived from the code registry, not the database."""

    slug: str
    name: str
    category: str
    description: str
    icon: str
    input_label: str
    input_placeholder: str
    uses_documents: bool
    structured: bool
    examples: list[str]
    use_count: int = 0


class SkillRunRequest(BaseModel):
    input: str = Field(min_length=1, max_length=32000)
    # When present, the run is recorded in that conversation as a user/assistant pair. Running a
    # skill from the chat box and having the result vanish on the next render is not a feature.
    conversation_id: int | None = None


class SkillRunResponse(BaseModel):
    slug: str
    # Set when the run was recorded in a conversation.
    message_id: int | None = None
    output: str
    # Present only for skills that declare an output schema, so the UI can render fields.
    structured: dict | None = None
    citations: list = Field(default_factory=list)
    model: str | None
    tokens_in: int
    tokens_out: int
    latency_ms: int


# ------------------------------------------------------------- prompt templates
class PromptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body: str
    category: PromptCategory
    version: int
    parent_id: int | None
    is_current: bool
    use_count: int
    workspace_id: int | None
    created_at: datetime


class PromptCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=8000)
    category: PromptCategory = "custom"
    # False makes the prompt available in every one of the user's workspaces.
    workspace_scoped: bool = True


class PromptUpdate(BaseModel):
    """Any change here creates a new version rather than editing this one."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=8000)
    category: PromptCategory | None = None
