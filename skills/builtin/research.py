"""Answer a research question from the workspace's documents."""
from skills.base import Skill

SKILL = Skill(
    slug="research",
    name="Research",
    category="research",
    description="Answer a question from your uploaded documents, with citations.",
    icon="search",
    input_label="What do you want to know?",
    input_placeholder="What does the handbook say about the passing score?",
    examples=("What are the security requirements across all our policy documents?",),
    uses_documents=True,
    system_prompt="""Answer the question from the supplied document excerpts.

Cite the excerpt number in square brackets immediately after any claim that comes from it.

Where the excerpts disagree with each other, say so and quote both rather than silently picking
one. Where they do not answer the question, say that plainly before offering anything from
general knowledge, and mark clearly which part is which.

An answer that admits a gap is more useful than one that papers over it.""",
)
