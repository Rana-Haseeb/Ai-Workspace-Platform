"""Generate a structured report from notes or findings."""
from skills.base import Skill

SKILL = Skill(
    slug="report",
    name="Report generator",
    category="business",
    description="Turn findings into a structured report with a clear recommendation.",
    icon="file-text",
    input_label="What is the report about?",
    input_placeholder="Our Q3 retention numbers and what we think is causing the drop…",
    examples=("Write up a technical evaluation of three vector databases.",),
    uses_documents=True,
    system_prompt="""Write a structured report.

Sections, in this order:
1. **Summary** — the conclusion, in three sentences. A reader who stops here should still know
   what you concluded and why.
2. **Background** — what prompted this.
3. **Findings** — what is actually true, with figures where they exist.
4. **Recommendation** — what to do, and what it costs.
5. **What we do not know** — the honest limits. Never omit this section.

Where document excerpts are supplied, cite them by number and prefer them to your own knowledge.
Distinguish clearly between what the evidence shows and what you are inferring from it.""",
)
