"""Break a goal into an ordered, estimated plan."""
from pydantic import BaseModel, Field

from skills.base import Skill


class PlanStep(BaseModel):
    step: str = Field(description="What to do")
    detail: str = Field(description="One sentence on how, or what makes it non-obvious")
    estimate: str = Field(description="Rough time, e.g. '2 hours', '1 day'")
    blocked_by: str = Field(description="Which earlier step must finish first, or 'nothing'")


class TaskPlan(BaseModel):
    goal: str = Field(description="The goal, restated precisely")
    steps: list[PlanStep] = Field(description="Ordered steps, 4-10 of them")
    first_action: str = Field(description="The single thing to do in the next hour")
    risks: list[str] = Field(description="What is most likely to go wrong")


SKILL = Skill(
    slug="task_planner",
    name="Task planner",
    category="productivity",
    description="Break a goal into ordered steps with estimates and dependencies.",
    icon="list-checks",
    input_label="What are you trying to achieve?",
    input_placeholder="Ship a beta of the mobile app to 50 testers…",
    examples=("Migrate our search from Elasticsearch to pgvector.",),
    output_schema=TaskPlan,
    system_prompt="""Break the stated goal into a plan that could be started today.

Steps must be **actions**, not areas. "Set up the database" is a step; "database work" is not.

Order them so dependencies come first, and say explicitly what each step is blocked by. Estimate
in hours or days, and prefer an honest wide estimate to a precise wrong one.

The first action must be small enough to start within the hour. The most common reason a plan
never gets started is that step one is too big.

List the risks that would actually derail this, not generic ones.""",
)
