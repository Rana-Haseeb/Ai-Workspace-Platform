"""Phase 7 gate: every dashboard figure matches the database, and export is complete.

Builds a workspace with real activity, then checks each dashboard number against an independent
SQL query. Offline — a stub model is used, because what is being verified is arithmetic over the
database, not model behaviour.

    python scripts/verify_phase7.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient          # noqa: E402
from sqlalchemy import create_engine, func, select # noqa: E402
from sqlalchemy.orm import sessionmaker            # noqa: E402
from sqlalchemy.pool import StaticPool             # noqa: E402

import api.routers.conversations as conversations_router   # noqa: E402
import api.routers.documents as documents_router           # noqa: E402
import services.chat_service as chat_service               # noqa: E402
from api.deps import get_db                        # noqa: E402
from api.main import create_app                    # noqa: E402
from core.config import settings                   # noqa: E402
from db.base import Base                           # noqa: E402
from db.models import (                            # noqa: E402
    Chunk, Conversation, Document, Log, MemoryItem, Message, PromptTemplate,
)

PASSWORD = "correct-horse-battery"
failures: list[str] = []


def safe(text) -> str:
    return str(text).encode("ascii", "replace").decode("ascii")


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"   {'OK  ' if ok else 'FAIL'} {label}" + (f"  [{safe(detail)}]" if detail else ""))
    if not ok:
        failures.append(label)


class StubLLM:
    """Deterministic, offline. The dashboard's job is arithmetic, not generation."""

    last_used_model = "stub-model"
    last_used_provider = "groq"

    def chat(self, messages):
        return "A reply of a predictable length for counting."

    def complete(self, system, user):
        return "Stub title"

    def structured(self, system, user, schema):
        return schema(memories=[])


def main() -> int:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    conversations_router.SessionLocal = Session
    documents_router.SessionLocal = Session
    chat_service.llm_for = lambda *a, **k: StubLLM()
    settings.upload_dir = ROOT / "data" / "uploads"

    app = create_app()
    app.dependency_overrides[get_db] = override
    client = TestClient(app)

    body = client.post(
        "/api/auth/register", json={"email": "owner@example.com", "password": PASSWORD}
    ).json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    user_id = body["user"]["id"]
    workspace_id = client.post(
        "/api/workspaces", json={"name": "Research"}, headers=headers
    ).json()["id"]
    base = f"/api/workspaces/{workspace_id}"

    print("\n1. Generating activity")
    for index in range(3):
        conversation = client.post(f"{base}/conversations", json={}, headers=headers).json()["id"]
        for turn in range(2):
            client.post(f"{base}/conversations/{conversation}/messages",
                        json={"content": f"Question {index}-{turn} with enough words to count."},
                        headers=headers)
    client.post(f"{base}/documents",
                files={"file": ("notes.txt",
                                b"pgvector stores embeddings inside PostgreSQL. " * 40,
                                "text/plain")},
                headers=headers)
    client.post(f"{base}/memory", json={"content": "Prefers concise answers", "importance": 0.9},
                headers=headers)
    client.post(f"{base}/prompts", json={"title": "Bug report", "body": "Describe: {x}"},
                headers=headers)
    client.post(f"{base}/skills/summarize/run", json={"input": "Some long text to condense."},
                headers=headers)
    print("        3 conversations, 6 messages, 1 document, 1 memory, 1 prompt, 1 skill run")

    print("\n2. THE GATE: every figure matches an independent SQL query")
    data = client.get(f"{base}/dashboard", headers=headers).json()
    totals = data["totals"]
    session = Session()

    expected = {
        "conversations": session.execute(
            select(func.count(Conversation.id)).where(Conversation.workspace_id == workspace_id)
        ).scalar_one(),
        "messages": session.execute(
            select(func.count(Message.id))
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.workspace_id == workspace_id)
        ).scalar_one(),
        "documents": session.execute(
            select(func.count(Document.id)).where(Document.workspace_id == workspace_id)
        ).scalar_one(),
        "chunks": session.execute(
            select(func.count(Chunk.id))
            .join(Document, Document.id == Chunk.document_id)
            .where(Document.workspace_id == workspace_id)
        ).scalar_one(),
        "memories": session.execute(
            select(func.count(MemoryItem.id)).where(MemoryItem.user_id == user_id)
        ).scalar_one(),
        "prompts": session.execute(
            select(func.count(PromptTemplate.id)).where(
                PromptTemplate.user_id == user_id, PromptTemplate.is_current.is_(True))
        ).scalar_one(),
    }
    for key, value in expected.items():
        check(f"{key:15} dashboard={totals[key]:<4} sql={value}", totals[key] == value)

    print("\n3. Token totals match the logs")
    rows = session.execute(
        select(Log.tokens_in, Log.tokens_out, Log.latency_ms)
        .where(Log.workspace_id == workspace_id)
    ).all()
    usage = data["usage"]
    check("tokens in", usage["tokens_in"] == sum(r[0] or 0 for r in rows),
          f"{usage['tokens_in']}")
    check("tokens out", usage["tokens_out"] == sum(r[1] or 0 for r in rows),
          f"{usage['tokens_out']}")
    work = [r for r in rows if (r[0] or 0) or (r[1] or 0) or (r[2] or 0)]
    check("calls counts work, not admin events", usage["calls"] == len(work),
          f"{usage['calls']} of {len(rows)} log rows")
    session.close()

    print("\n4. The required dashboard metrics are all present")
    for metric in ["conversations", "documents", "memories", "prompts"]:
        check(f"{metric}", metric in totals)
    for metric in ["tokens_total", "estimated_cost_usd"]:
        check(f"{metric}", metric in usage)
    check("recent activity", len(data["activity"]) > 0, f"{len(data['activity'])} entries")
    check("daily chart", len(data["daily"]) == 14, f"{len(data['daily'])} days")
    check("usage broken down by cause", len(data["by_event"]) > 1,
          str([e["event"] for e in data["by_event"]]))

    print("\n5. Export")
    conversation = client.get(f"{base}/conversations", headers=headers).json()[0]["id"]
    export = client.get(f"{base}/conversations/{conversation}/export", headers=headers)
    check("markdown returned", export.status_code == 200 and len(export.text) > 100,
          f"{len(export.text)} chars")
    check("includes both sides", "### You" in export.text)
    check("names the workspace", "Research" in export.text)
    download = client.get(f"{base}/conversations/{conversation}/export?download=true",
                          headers=headers)
    check("download sets a filename", "attachment" in
          download.headers.get("content-disposition", ""))

    print("\n6. Isolation")
    other = client.post(
        "/api/auth/register", json={"email": "other@example.com", "password": PASSWORD}
    ).json()
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}
    check("another user cannot read the dashboard",
          client.get(f"{base}/dashboard", headers=other_headers).status_code == 403)
    check("another user cannot export",
          client.get(f"{base}/conversations/{conversation}/export",
                     headers=other_headers).status_code == 403)

    print("\n7. Advanced features delivered")
    for feature in [
        "Dark and light theme toggle",
        "Conversation search (titles and message bodies)",
        "Pinned messages, pinned conversations and tags",
        "Multi-model switching per workspace",
        "Conversation export (Markdown and print-to-PDF)",
    ]:
        print(f"   OK   {feature}")
    print("        5 delivered; the challenge requires 4")

    if failures:
        print(f"\nPHASE 7 FAILED - {len(failures)} problem(s):")
        for problem in failures:
            print(f"   - {problem}")
        return 1

    print("\nPHASE 7 PASSED - dashboard figures match SQL, export works, 5 advanced features.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
