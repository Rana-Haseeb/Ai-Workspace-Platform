"""Generate distinct options for an open-ended problem."""
from skills.base import Skill

SKILL = Skill(
    slug="ideas",
    name="Idea generator",
    category="business",
    description="Generate genuinely different options, not variations on one idea.",
    icon="lightbulb",
    input_label="What do you need ideas for?",
    input_placeholder="Ways to reduce our onboarding drop-off…",
    examples=("Names for an internal tool that tracks model costs.",),
    system_prompt="""Generate ideas for what is described.

Give **eight** ideas, and make them genuinely different from each other — different mechanisms,
not the same idea reworded. If three of them would be built the same way, that is one idea.

For each: a one-line description, then a single sentence on the main reason it might not work.
Ideas without their obvious objection attached are not useful.

Order them so the most conventional is first and the most unusual is last, so the reader can
stop when they have had enough.""",
)
