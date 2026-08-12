"""Review code for correctness, clarity and risk."""
from skills.base import Skill

SKILL = Skill(
    slug="code_review",
    name="Code reviewer",
    category="programming",
    description="Review code for bugs, clarity and things that will hurt later.",
    icon="code",
    input_label="Code to review",
    input_placeholder="Paste a function, a diff, or a whole file…",
    examples=("Review this SQL query for injection risk and performance.",),
    system_prompt="""Review the code provided.

Order findings by how much they matter, most serious first, and group them:
- **Bugs** — it does the wrong thing. Say what input triggers it.
- **Risks** — it works now and will bite later: unhandled failure, race, resource leak,
  injection, unbounded growth.
- **Clarity** — a future reader will misunderstand it.

For each finding give the specific line or expression and a concrete fix, not a principle.

If the code is fine, say so in one line. Manufacturing findings to look thorough wastes the
reader's time and trains them to ignore you. Never comment on formatting a formatter would fix.""",
)
