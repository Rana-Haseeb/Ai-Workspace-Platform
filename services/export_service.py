"""Exporting a conversation.

Markdown, not PDF, is generated here — and that is a deliberate limit rather than an omission.
A server-side PDF means a rendering engine (WeasyPrint, wkhtmltopdf, a headless browser) as a
dependency, and every one of them is heavy, awkward to install, and a new failure mode in
production. The browser already has an excellent PDF renderer, so the client prints a clean
export view and the platform ships one fewer dependency. The README says so plainly.

Markdown also happens to be the better artefact: it opens anywhere, diffs, and pastes into a
document without losing structure.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from db.models import Conversation, Workspace
from services import chat_service


def _format_citations(citations: list) -> str:
    if not citations:
        return ""
    lines = ["", "> **Sources**"]
    for index, citation in enumerate(citations, start=1):
        page = f", page {citation['page']}" if citation.get("page") else ""
        lines.append(f"> {index}. {citation.get('filename', 'unknown')}{page}")
    return "\n".join(lines)


def _format_memory(memories: list) -> str:
    if not memories:
        return ""
    lines = ["", "> **Applied from memory**"]
    for item in memories:
        lines.append(f"> - {item.get('content', '')}")
    return "\n".join(lines)


def conversation_to_markdown(
    db: Session, workspace: Workspace, conversation: Conversation, include_metadata: bool = True
) -> str:
    """One conversation as a Markdown document.

    Citations and applied memories are included as block quotes under the message they belong to,
    so an exported answer carries the same evidence the screen did. An export that silently drops
    the sources turns a checkable answer back into an unsourced assertion.
    """
    messages = chat_service.history_for(db, conversation.id)

    parts = [
        f"# {conversation.title}",
        "",
        f"**Workspace:** {workspace.name}  ",
        f"**Assistant:** {workspace.settings.assistant_name}  ",
        f"**Started:** {conversation.created_at:%Y-%m-%d %H:%M} UTC  ",
        f"**Messages:** {len(messages)}",
    ]
    if conversation.tags:
        parts.append(f"**Tags:** {', '.join(conversation.tags)}")
    parts.extend(["", "---", ""])

    for message in messages:
        if message.role == "user":
            parts.append(f"### You")
        else:
            heading = f"### {workspace.settings.assistant_name}"
            if include_metadata and message.model:
                heading += f"  \n`{message.model}` · {message.latency_ms / 1000:.1f}s"
            parts.append(heading)

        parts.extend(["", message.content])

        if message.role == "assistant":
            citations = _format_citations(message.citations or [])
            if citations:
                parts.append(citations)
            memory = _format_memory(message.memory_used or [])
            if memory:
                parts.append(memory)

        parts.extend(["", ""])

    if include_metadata:
        tokens = sum((m.tokens_in or 0) + (m.tokens_out or 0) for m in messages)
        parts.extend([
            "---",
            "",
            f"*Exported from AI Workspace Platform. Approximately {tokens:,} tokens across "
            f"{len([m for m in messages if m.role == 'assistant'])} replies.*",
        ])

    return "\n".join(parts)


def safe_filename(title: str, extension: str = "md") -> str:
    """A filename a browser and a filesystem will both accept."""
    cleaned = "".join(character if character.isalnum() or character in " -_" else "-"
                      for character in title).strip()
    cleaned = "-".join(cleaned.split()) or "conversation"
    return f"{cleaned[:60]}.{extension}"
