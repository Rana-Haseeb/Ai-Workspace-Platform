"""Phase 0 gate: the foundations are real.

Checks four things and prints what it found, so the result is evidence rather than a claim:

  1. All twelve required tables exist in the live database.
  2. The assistant-settings table carries all eight configurable fields.
  3. Every user-scoped foreign key is indexed.
  4. ``.env`` is ignored by git, so a filled-in key can never be committed.

    python scripts/verify_phase0.py

Exits non-zero on any failure.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect                    # noqa: E402

from core.config import settings                  # noqa: E402
from db.base import Base, engine                  # noqa: E402
from db.models import ALL_TABLES                  # noqa: E402
import db.models                                  # noqa: E402,F401

SETTINGS_FIELDS = [
    "assistant_name", "role", "system_prompt", "model",
    "temperature", "max_tokens", "personality", "response_style",
]
OWNER_KEYS = [
    ("workspaces", "user_id"),
    ("prompt_templates", "user_id"),
    ("memory_items", "user_id"),
    ("conversations", "workspace_id"),
    ("documents", "workspace_id"),
    ("messages", "conversation_id"),
    ("chunks", "document_id"),
]


def _tick(ok: bool) -> str:
    return "OK  " if ok else "FAIL"


def main() -> int:
    failures: list[str] = []
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    present = set(inspector.get_table_names())

    print(f"\nDatabase: {'SQLite' if settings.is_sqlite() else 'PostgreSQL'}")

    print("\n1. Required tables")
    for table in ALL_TABLES:
        if table in present:
            count = len(inspector.get_columns(table))
            print(f"   {_tick(True)} {table:<20} {count:>2} columns")
        else:
            print(f"   {_tick(False)} {table:<20} MISSING")
            failures.append(f"table {table} missing")

    print("\n2. Assistant settings fields")
    columns = {c["name"] for c in inspector.get_columns("settings")} if "settings" in present else set()
    for field in SETTINGS_FIELDS:
        ok = field in columns
        print(f"   {_tick(ok)} {field}")
        if not ok:
            failures.append(f"settings.{field} missing")

    print("\n3. Indexes on ownership keys")
    for table, column in OWNER_KEYS:
        indexed = {
            col for index in inspector.get_indexes(table) for col in index["column_names"]
        } if table in present else set()
        ok = column in indexed
        print(f"   {_tick(ok)} {table}.{column}")
        if not ok:
            failures.append(f"{table}.{column} not indexed")

    print("\n4. Secrets hygiene")
    result = subprocess.run(
        ["git", "check-ignore", "-v", ".env"], cwd=ROOT, capture_output=True, text=True
    )
    ok = result.returncode == 0
    print(f"   {_tick(ok)} .env is gitignored" + (f"  [{result.stdout.strip()}]" if ok else ""))
    if not ok:
        failures.append(".env is NOT gitignored")

    print("\n5. Frontend theme tokens")
    css = (ROOT / "web" / "src" / "index.css")
    css_text = css.read_text(encoding="utf-8") if css.exists() else ""
    for label, needle in [
        ("light theme block", ":root {"),
        ("dark theme block", ".dark {"),
        ("Inter font", "Inter Variable"),
        ("reduced-motion guard", "prefers-reduced-motion"),
        ("no pure black surface", "oklch(0 0"),
    ]:
        # The last check is an absence check: a pure-black surface must NOT appear.
        ok = (needle not in css_text) if label.startswith("no ") else (needle in css_text)
        print(f"   {_tick(ok)} {label}")
        if not ok:
            failures.append(f"index.css: {label}")

    if failures:
        print(f"\nPHASE 0 FAILED - {len(failures)} problem(s):")
        for problem in failures:
            print(f"   - {problem}")
        return 1

    print(f"\nPHASE 0 PASSED - {len(ALL_TABLES)} tables, "
          f"{len(SETTINGS_FIELDS)} settings fields, {len(OWNER_KEYS)} indexed keys, "
          f"2 themes.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
