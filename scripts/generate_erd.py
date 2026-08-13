"""Generate ``docs/ERD.md`` from the SQLAlchemy metadata.

    python scripts/generate_erd.py
    python scripts/generate_erd.py --check    # fail if the committed file is stale

Read from ``Base.metadata``, not from a drawing. A hand-maintained diagram is a picture of what
the schema looked like when somebody last remembered to update it; this one cannot show a column
that was renamed or miss a table that was added, and ``--check`` in the Phase 10 gate is what
keeps the committed copy honest.

Commentary the metadata cannot carry — *why* a table is shaped the way it is — lives in ``NOTES``.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "docs" / "ERD.md"

# Presentation order: roughly the order data flows through the platform.
ORDER = ["users", "workspaces", "settings", "conversations", "messages", "documents",
         "chunks", "embeddings", "memory_items", "prompt_templates", "skills", "logs"]

PURPOSE = {
    "users": "An account. The root of every ownership chain.",
    "workspaces": "The unit of isolation. Owns its conversations, documents and configuration.",
    "settings": "One assistant configuration per workspace — the eight tunable fields.",
    "conversations": "A chat thread inside a workspace.",
    "messages": "One turn. Carries its own citations, token counts, cost and latency.",
    "documents": "An uploaded file and its ingestion status.",
    "chunks": "A slice of a document, remembering the page it came from.",
    "embeddings": "One vector per chunk.",
    "memory_items": "What the assistant remembers about a user.",
    "prompt_templates": "The prompt library. Versioned by insertion, never mutation.",
    "skills": "Mirrors the code registry so skills are listable and countable.",
    "logs": "Every billable event. Powers the dashboard.",
}

NOTES = """
## Four decisions worth defending

### 1. `prompt_templates.parent_id` — versioning by insertion

Editing a prompt **inserts a new row** pointing at its parent and increments `version`. Nothing is
ever overwritten.

The alternative — updating the row in place — silently rewrites history: a conversation that ran
against version 1 would, when reopened, appear to have used version 3. Since the whole platform
is built on being able to say *where an answer came from*, a prompt that changes underneath a
past answer breaks the one promise that matters. The cost is rows that accumulate; the benefit is
that an old conversation still points at the exact text that produced it.

### 2. `messages.citations` is denormalised JSON

Citations could be a join table onto `chunks`. They are stored on the message instead.

A citation is a record of *what the model was actually shown*, not a live pointer. If the user
deletes the document, the old answer must still show what it was based on — a join would either
break or, worse, quietly resolve to a different chunk after re-ingestion. The same reasoning
applies to `memory_used`. This trades normal form for the ability to answer "why did it say
that?" a month later, which is the trade this platform exists to make.

### 3. `embeddings.vector` is JSON, behind an interface

Vectors are stored as JSON arrays and compared in Python. That is honest about what it is: fine
at thousands of chunks, wrong at millions, because every query loads every vector in the
workspace.

It is written behind a `VectorStore` interface so pgvector can replace it without touching a
single caller. Reaching for pgvector on day one would have meant a Postgres dependency for local
development and the test suite, to solve a scaling problem the project does not yet have.

### 4. Every ownership path leads back to `users` in one hop or two

`workspaces.user_id` is the only branch point. Documents, conversations, chunks and messages
inherit isolation through their workspace rather than each carrying their own `user_id`.

One chain means one place to check, which is why `get_owned_workspace` can be a single dependency
rather than a rule every route re-implements. `memory_items` and `prompt_templates` carry
`user_id` directly and a **nullable** `workspace_id`, because a preference like *"answer in
British English"* belongs to the person, not to one of their workspaces.

## Cascades

Foreign keys are declared `ON DELETE CASCADE` down each ownership chain, so deleting a workspace
removes its conversations, messages, documents, chunks and embeddings.

SQLite ships with foreign-key enforcement **off**, so `PRAGMA foreign_keys=ON` is issued on every
connection in `tests/conftest.py`. Without it a cascade test passes while cascading nothing —
the deletion appears to work and orphans accumulate.
"""


def build() -> str:
    from sqlalchemy import inspect as sa_inspect  # noqa: F401  (kept for parity of imports)

    from db.base import Base
    import db.models  # noqa: F401 — registers the tables

    tables = {t.name: t for t in Base.metadata.sorted_tables}
    ordered = [tables[n] for n in ORDER if n in tables] + \
              [t for n, t in sorted(tables.items()) if n not in ORDER]

    total_columns = sum(len(t.columns) for t in ordered)
    total_fks = sum(len([c for c in t.columns if c.foreign_keys]) for t in ordered)

    lines: list[str] = [
        "# Entity Relationship Diagram",
        "",
        "**Generated from `db/models.py` — do not edit the diagram or the tables by hand.**",
        "",
        "```bash",
        "python scripts/generate_erd.py",
        "```",
        "",
        f"**{len(ordered)} tables**, {total_columns} columns, {total_fks} foreign keys.",
        "",
        "---",
        "",
        "## Diagram",
        "",
        "```mermaid",
        "erDiagram",
    ]

    for table in ordered:
        for column in table.columns:
            for fk in column.foreign_keys:
                parent = fk.column.table.name
                if parent == table.name:
                    # The self-reference on prompt_templates: a row points at the version it
                    # replaced.
                    lines.append(f"    {parent} ||--o{{ {table.name} : \"supersedes\"")
                    continue

                # A unique foreign key is a one-to-one, and drawing it as one-to-many would
                # misstate the schema. `settings` and `embeddings` are both 1:1 by constraint,
                # not by convention.
                if column.unique:
                    cardinality = "||--o|" if column.nullable else "||--||"
                    label = "has one"
                else:
                    cardinality = "||--o{"
                    label = f"{column.name}{' (optional)' if column.nullable else ''}"
                lines.append(f"    {parent} {cardinality} {table.name} : \"{label}\"")

    lines.append("```")
    lines.append("")
    lines.append("`skills` has no foreign key: it mirrors the code registry in `skills/` and is "
                 "global rather than owned.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Tables")
    lines.append("")

    for table in ordered:
        lines.append(f"### `{table.name}`")
        lines.append("")
        if table.name in PURPOSE:
            lines.append(PURPOSE[table.name])
            lines.append("")
        lines.append("| Column | Type | Null | Key | Default |")
        lines.append("|---|---|:--:|---|---|")
        for column in table.columns:
            keys = []
            if column.primary_key:
                keys.append("PK")
            for fk in column.foreign_keys:
                keys.append(f"FK → `{fk.target_fullname}`")
            if column.unique:
                keys.append("unique")
            if column.index:
                keys.append("indexed")

            default = "—"
            if column.default is not None and getattr(column.default, "arg", None) is not None:
                arg = column.default.arg
                default = f"`{arg}`" if not callable(arg) else "generated"
            elif column.server_default is not None:
                default = "server"

            lines.append(
                f"| `{column.name}` | {column.type} | "
                f"{'yes' if column.nullable else 'no'} | {', '.join(keys) or '—'} | {default} |"
            )
        lines.append("")

    lines.append("---")
    lines.append(NOTES.strip())
    lines.append("")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    generated = build()
    if args.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != generated:
            print(f"FAIL {OUT.relative_to(ROOT)} is stale — the schema changed. Regenerate it.")
            return 1
        print(f"OK   {OUT.relative_to(ROOT)} matches db/models.py.")
        return 0

    OUT.write_text(generated, encoding="utf-8")
    print(f"Written -> {OUT.relative_to(ROOT)} ({len(generated.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
