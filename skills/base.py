"""What a skill is.

A skill is **data, not code**: a system prompt plus enough metadata to render it and run it.
That choice is deliberate and it has one concrete consequence — adding a skill is a single new
file and a single line in the registry, with no new execution path to test.

The alternative, a class per skill with its own ``run`` method, buys flexibility that almost no
skill actually needs and costs a new code path for every one. Where a skill genuinely benefits
from structure (a SWOT is four lists, not a paragraph), it declares an ``output_schema`` and the
shared runner switches to structured output. That covers the real variation without giving every
skill its own machinery.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel

CATEGORIES = ("writing", "programming", "research", "business", "education", "productivity")


@dataclass(frozen=True)
class Skill:
    """One reusable capability, available in every workspace."""

    slug: str
    name: str
    category: str
    description: str
    # lucide-react icon name. Never an emoji — see the design system notes in the README.
    icon: str
    # Sent as the system message. This is the whole behaviour of the skill.
    system_prompt: str
    # What the input box asks for, and an example of a good answer.
    input_label: str = "Input"
    input_placeholder: str = ""
    # When true the workspace's documents are searched and the excerpts are supplied, so the
    # skill's output can carry citations.
    uses_documents: bool = False
    # Optional structured output. When set, the runner asks the model for this shape instead of
    # free text, and the UI renders the fields rather than a wall of prose.
    output_schema: type[BaseModel] | None = None
    # Example inputs, shown in the UI so a skill is never a blank box.
    examples: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.category not in CATEGORIES:
            raise ValueError(
                f"Skill {self.slug!r} has category {self.category!r}; "
                f"expected one of {CATEGORIES}"
            )
        if not self.system_prompt.strip():
            raise ValueError(f"Skill {self.slug!r} has an empty system prompt")


@dataclass
class SkillResult:
    """What running a skill produced."""

    slug: str
    output: str
    structured: dict | None = None
    citations: list = field(default_factory=list)
    model: str | None = None
    provider: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    # Set when the run was recorded in a conversation.
    message_id: int | None = None
