"""Prove the schema works on the production database, before deployment day.

The whole "SQLite locally, Postgres in production" claim rests on one set of models running
unchanged on both. This is what checks that, against the real server:

    DATABASE_URL="postgresql://..." python scripts/check_postgres.py

Or, if the URL is parked in .env under a different name:

    python scripts/check_postgres.py --from-env NEON_DATABASE_URL

It creates every table, writes a row through the full relationship tree, reads it back, checks
the cascade, and cleans up after itself. Nothing is left behind.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

parser = argparse.ArgumentParser()
parser.add_argument("--from-env", default=None,
                    help="Name of another env var holding the connection string")
parser.add_argument("--keep", action="store_true", help="Leave the tables in place afterwards")
args = parser.parse_args()

if args.from_env:
    url = os.getenv(args.from_env)
    if not url:
        print(f"\n{args.from_env} is not set in the environment or .env\n")
        raise SystemExit(1)
    # Must happen before core.config is imported, since Settings reads the environment once.
    os.environ["DATABASE_URL"] = url

from sqlalchemy import inspect, text            # noqa: E402

from core.config import settings                # noqa: E402
from db.base import DATABASE_URL, Base, SessionLocal, engine   # noqa: E402
from db.models import (                         # noqa: E402
    ALL_TABLES,
    AssistantSettings,
    Chunk,
    Conversation,
    Document,
    Embedding,
    Message,
    User,
    Workspace,
)

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"   {'OK  ' if ok else 'FAIL'} {label}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        failures.append(label)


def main() -> int:
    if settings.is_sqlite():
        print("\nDATABASE_URL points at SQLite. Pass a Postgres URL to check the production path.\n")
        return 1

    # Never print the URL: it carries the password.
    host = DATABASE_URL.split("@")[-1].split("/")[0]
    print(f"\nDriver : {DATABASE_URL.split('://')[0]}")
    print(f"Host   : {host}")

    print("\n1. Connection")
    started = time.perf_counter()
    with engine.connect() as conn:
        version = conn.execute(text("select version()")).scalar() or ""
    check("connected", True, f"{time.perf_counter() - started:.2f}s")
    print(f"        {version.split(' on ')[0]}")

    print("\n2. Schema")
    started = time.perf_counter()
    Base.metadata.create_all(engine)
    elapsed = time.perf_counter() - started
    present = set(inspect(engine).get_table_names())
    missing = set(ALL_TABLES) - present
    check("all 12 tables created", not missing,
          f"{len(set(ALL_TABLES) & present)}/12 in {elapsed:.2f}s")
    if missing:
        print(f"        missing: {sorted(missing)}")

    print("\n3. A full write, read and cascade")
    db = SessionLocal()
    user_id = None
    try:
        marker = f"pgcheck-{int(time.time())}@example.com"
        user = User(email=marker, password_hash="x")
        workspace = Workspace(name="Postgres check")
        workspace.settings = AssistantSettings()

        conversation = Conversation(session_id="s1", title="Check")
        conversation.messages.append(
            Message(role="assistant", content="hello",
                    citations=[{"page": 1, "filename": "a.pdf"}])
        )
        workspace.conversations.append(conversation)

        document = Document(filename="a.pdf", stored_path="/tmp/a.pdf",
                            mime_type="application/pdf", size_bytes=1)
        chunk = Chunk(ordinal=0, text="body", page=1)
        chunk.embedding = Embedding(model="test", dim=3, vector=[0.1, 0.2, 0.3])
        document.chunks.append(chunk)
        workspace.documents.append(document)

        user.workspaces.append(workspace)
        db.add(user)
        db.commit()
        user_id = user.id
        check("wrote the whole tree", user_id is not None, f"user id {user_id}")

        stored = db.get(Message, conversation.messages[0].id)
        check("JSON column round-trips", stored.citations[0]["page"] == 1,
              str(stored.citations))
        stored_vec = db.get(Embedding, chunk.embedding.id)
        check("vector column round-trips", stored_vec.vector == [0.1, 0.2, 0.3],
              str(stored_vec.vector))

        db.delete(db.get(User, user_id))
        db.commit()
        user_id = None
        remaining = (
            db.query(Workspace).count()
            + db.query(Message).count()
            + db.query(Embedding).count()
        )
        check("cascade delete removed everything", remaining == 0, f"{remaining} rows left")
    finally:
        if user_id is not None:
            db.delete(db.get(User, user_id))
            db.commit()
        db.close()

    print("\n4. pgvector, for the day the JSON store stops being enough")
    with engine.connect() as conn:
        available = conn.execute(
            text("select count(*) from pg_available_extensions where name='vector'")
        ).scalar()
    print(f"   {'OK  ' if available else '--  '} pgvector "
          f"{'available on this server' if available else 'not offered by this provider'}")

    if not args.keep:
        Base.metadata.drop_all(engine)
        print("\n   (tables dropped; pass --keep to leave them in place)")

    if failures:
        print(f"\nPOSTGRES CHECK FAILED - {len(failures)} problem(s):")
        for problem in failures:
            print(f"   - {problem}")
        return 1

    print("\nPOSTGRES CHECK PASSED - the same models run unchanged on this server.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
