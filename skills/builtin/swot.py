"""Structured strategic analysis: strengths, weaknesses, opportunities, threats."""
from pydantic import BaseModel, Field

from skills.base import Skill


class SwotAnalysis(BaseModel):
    """Four lists, because a SWOT rendered as prose is not a SWOT."""

    subject: str = Field(description="What is being analysed")
    strengths: list[str] = Field(description="Internal advantages, 3-5 items")
    weaknesses: list[str] = Field(description="Internal disadvantages, 3-5 items")
    opportunities: list[str] = Field(description="External factors that could help, 3-5 items")
    threats: list[str] = Field(description="External factors that could hurt, 3-5 items")
    recommendation: str = Field(description="One paragraph: what to do about it")


SKILL = Skill(
    slug="swot",
    name="SWOT analysis",
    category="business",
    description="Strengths, weaknesses, opportunities and threats, with a recommendation.",
    icon="layout-grid",
    input_label="What should I analyse?",
    input_placeholder="A product, a company, a decision you are weighing…",
    examples=("Launching a paid tier for our developer tool in Q3.",),
    output_schema=SwotAnalysis,
    system_prompt="""Produce a SWOT analysis of whatever the user names.

Keep strengths and weaknesses **internal** — things the subject controls. Keep opportunities and
threats **external** — things happening regardless. Confusing the two is the most common way a
SWOT becomes useless.

Each item is one specific sentence. "Strong team" is not an item; "three engineers with prior
payments experience" is.

Finish with a recommendation that follows from the four lists rather than restating them.""",
)
