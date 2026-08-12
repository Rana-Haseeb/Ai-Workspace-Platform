"""Draft a professional email from a rough intent."""
from skills.base import Skill

SKILL = Skill(
    slug="email",
    name="Email draft",
    category="writing",
    description="Turn a rough intent into a clear, polite email.",
    icon="mail",
    input_label="What do you need to say, and to whom?",
    input_placeholder="Tell my client the API integration will slip by a week…",
    examples=("Ask a supplier for a revised quote without sounding annoyed.",),
    system_prompt="""Draft an email that says what the user needs to say.

Rules:
- Subject line first, on its own line, prefixed "Subject: ".
- Lead with the point. Nobody reads to the third paragraph to find out what you want.
- Match the register the situation calls for: bad news is direct and takes responsibility;
  a request is specific about what is needed and by when.
- No filler openings ("I hope this email finds you well") and no thanking someone in advance
  for something they have not agreed to.

If something needed is missing — a name, a date, an amount — leave a clearly marked
[placeholder] rather than inventing it.""",
)
