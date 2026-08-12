"""Running a skill.

One execution path for every skill, which is what makes a skill cheap to add. The only branch is
whether the skill declared an ``output_schema``: with one, the model is asked for that shape and
the result is both structured and rendered as text; without one, it returns prose.

Skills reuse the workspace's assistant configuration — its model, temperature and token ceiling —
so a workspace tuned for terse technical answers gets terse technical skill output too. What they
deliberately do **not** reuse is the workspace system prompt: a skill's instructions are the
skill, and layering a persona on top is how a SWOT ends up written in the second person.
"""
from __future__ import annotations

import time

from sqlalchemy.orm import Session

from core.logging import get_logger
from db.models import Conversation, Log, Skill as SkillRow, Workspace
from services import chat_service, retrieval_service
from services.llm_service import LLMError
from skills import registry
from skills.base import Skill, SkillResult

log = get_logger("skills")


class UnknownSkill(Exception):
    """No skill is registered under that slug."""


def _render(structured: dict) -> str:
    """A readable text form of a structured result.

    Every skill produces text as well as structure: the text is what gets copied into an email or
    a document, and what a plain-text export contains. Deriving it from the structure rather than
    asking the model twice keeps the two from disagreeing.
    """
    lines: list[str] = []
    for key, value in structured.items():
        label = key.replace("_", " ").capitalize()
        if isinstance(value, list):
            if not value:
                continue
            lines.append(f"## {label}")
            for entry in value:
                if isinstance(entry, dict):
                    parts = [str(v) for v in entry.values() if v]
                    lines.append(f"- {' — '.join(parts)}")
                else:
                    lines.append(f"- {entry}")
            lines.append("")
        elif value:
            lines.append(f"## {label}")
            lines.append(str(value))
            lines.append("")
    return "\n".join(lines).strip()


def run(
    db: Session,
    workspace: Workspace,
    slug: str,
    user_input: str,
    user_id: int,
    conversation: Conversation | None = None,
) -> SkillResult:
    """Execute one skill against one input.

    With a ``conversation``, the exchange is written into it as a normal user/assistant pair, so
    a skill run from the chat box survives a reload and appears in the transcript alongside
    everything else. Without one — the Skills page — the result is returned and not stored.
    """
    skill: Skill | None = registry.get(slug)
    if skill is None:
        raise UnknownSkill(slug)

    settings_row = workspace.settings
    citations: list = []
    prompt = user_input

    if skill.uses_documents and settings_row.use_knowledge_base:
        retrieved = chat_service.retrieve_context(db, workspace, settings_row, user_input)
        citations = [c.to_dict() for c in retrieved.citations]
        block = retrieved.context_block()
        if block:
            prompt = (
                f"{retrieval_service.GROUNDING_INSTRUCTION}\n\n"
                f"Excerpts from the user's documents:\n\n{block}\n\n"
                f"---\n\n{user_input}"
            )

    client = chat_service.llm_for(settings_row, agent_id=f"skill:{slug}")
    started = time.perf_counter()

    structured: dict | None = None
    if skill.output_schema is not None:
        result = client.structured(
            system=skill.system_prompt, user=prompt, schema=skill.output_schema
        )
        structured = result.model_dump()
        output = _render(structured)
    else:
        output = client.complete(system=skill.system_prompt, user=prompt)

    latency_ms = int((time.perf_counter() - started) * 1000)

    _record_usage(db, skill, workspace, user_id, client, prompt, output, latency_ms)

    message_id = None
    if conversation is not None:
        chat_service.record_user_message(db, conversation, f"/{slug} {user_input}")
        assistant_message = chat_service.record_assistant_message(
            db, conversation, output,
            model=client.last_used_model,
            provider=client.last_used_provider,
            tokens_in=len(prompt) // 4,
            tokens_out=len(output) // 4,
            latency_ms=latency_ms,
            user_id=user_id,
            citations=citations,
        )
        message_id = assistant_message.id
        if not conversation.messages or conversation.title == "New conversation":
            conversation.title = f"{skill.name}: {user_input[:40]}"
            db.commit()

    return SkillResult(
        message_id=message_id,
        slug=slug,
        output=output,
        structured=structured,
        citations=citations,
        model=client.last_used_model,
        provider=client.last_used_provider,
        tokens_in=len(prompt) // 4,
        tokens_out=len(output) // 4,
        latency_ms=latency_ms,
    )


def _record_usage(db, skill, workspace, user_id, client, prompt, output, latency_ms) -> None:
    """Count the run and log it, so the dashboard can show which skills earn their place.

    The row is created if it is missing rather than assumed to exist. ``sync_registry`` normally
    populates the table at startup, but depending on that ordering means the count silently
    no-ops whenever it has not run — in a test, in a script, or on the first request after a
    skill is added but before a restart. Upserting removes the dependency entirely.
    """
    row = db.query(SkillRow).filter_by(slug=skill.slug).one_or_none()
    if row is None:
        row = SkillRow(
            slug=skill.slug, name=skill.name, category=skill.category,
            description=skill.description, icon=skill.icon,
        )
        db.add(row)
    # `or 0` because a column default is applied on INSERT, not on construction: a row created
    # a line above still has use_count=None until it is flushed.
    row.use_count = (row.use_count or 0) + 1

    db.add(Log(
        user_id=user_id,
        workspace_id=workspace.id,
        event="skill",
        detail=skill.slug,
        provider=client.last_used_provider,
        model=client.last_used_model,
        tokens_in=len(prompt) // 4,
        tokens_out=len(output) // 4,
        latency_ms=latency_ms,
        status="ok",
    ))
    db.commit()


def sync_registry(db: Session) -> int:
    """Mirror the code registry into the ``skills`` table.

    The registry is the source of truth for *behaviour*; the table exists so skills can be listed,
    filtered and counted in SQL alongside everything else the dashboard reads. Running this on
    startup means adding a skill needs no migration and no manual insert — it appears the next
    time the server boots.
    """
    existing = {row.slug: row for row in db.query(SkillRow).all()}
    changed = 0

    for skill in registry.all_skills():
        row = existing.get(skill.slug)
        if row is None:
            db.add(SkillRow(
                slug=skill.slug, name=skill.name, category=skill.category,
                description=skill.description, icon=skill.icon,
            ))
            changed += 1
        elif (row.name, row.category, row.description, row.icon) != (
            skill.name, skill.category, skill.description, skill.icon
        ):
            row.name, row.category = skill.name, skill.category
            row.description, row.icon = skill.description, skill.icon
            changed += 1

    if changed:
        db.commit()
        log.info("Synced %d skill definitions into the database", changed)
    return changed
