"""Condense a long piece of text into something scannable."""
from skills.base import Skill

SKILL = Skill(
    slug="summarize",
    name="Summarise",
    category="writing",
    description="Turn a long text into a short summary with the key points pulled out.",
    icon="align-left",
    input_label="Text to summarise",
    input_placeholder="Paste an article, transcript, or report…",
    examples=("Paste a long email thread and get the decision out of it.",),
    system_prompt="""Summarise the text the user provides.

Structure:
1. One sentence saying what the text is about.
2. The key points as short bullets — only what is actually in the text.
3. Any decision, deadline or action mentioned, under a heading "What this asks of you". Omit
   this section entirely if there is nothing.

Preserve numbers, names and dates exactly. Do not add information that is not in the text, and
do not soften a conclusion the author stated plainly.""",
)
