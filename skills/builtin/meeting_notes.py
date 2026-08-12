"""Pull structure out of raw meeting notes or a transcript."""
from pydantic import BaseModel, Field

from skills.base import Skill


class ActionItem(BaseModel):
    task: str = Field(description="What needs doing")
    owner: str = Field(description="Who owns it, or 'unassigned'")
    due: str = Field(description="When, or 'not stated'")


class MeetingSummary(BaseModel):
    title: str = Field(description="A short title for the meeting")
    summary: str = Field(description="Two or three sentences on what happened")
    decisions: list[str] = Field(description="Decisions actually made")
    action_items: list[ActionItem] = Field(description="Concrete follow-ups")
    open_questions: list[str] = Field(description="Things left unresolved")


SKILL = Skill(
    slug="meeting_notes",
    name="Meeting notes",
    category="productivity",
    description="Extract decisions, owners and open questions from messy notes.",
    icon="clipboard-list",
    input_label="Notes or transcript",
    input_placeholder="Paste your rough notes — they do not need to be tidy…",
    examples=("Paste a call transcript and get the action items with owners.",),
    output_schema=MeetingSummary,
    system_prompt="""Turn the raw meeting notes into structure.

A **decision** is something that was settled. A **discussion** is not a decision — do not
promote one to the other because it sounds conclusive.

For every action item, name the owner if the notes name one and write "unassigned" if they do
not. Inventing an owner is worse than admitting there is not one.

Put anything raised but not resolved under open questions. That list is usually the most useful
part and the one people forget to write down.""",
)
