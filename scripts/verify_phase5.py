"""Phase 5 gate: something stated once is still known in a new session.

Live. A real model reads a real message, decides what is worth remembering, and a *different
application instance* applies it to a question that never mentions it.

    python scripts/verify_phase5.py

Needs a provider key. Exits non-zero on failure.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient          # noqa: E402
from sqlalchemy import create_engine               # noqa: E402
from sqlalchemy.orm import sessionmaker            # noqa: E402
from sqlalchemy.pool import StaticPool             # noqa: E402

import api.routers.conversations as conversations_router   # noqa: E402
import api.routers.documents as documents_router           # noqa: E402
from api.deps import get_db                        # noqa: E402
from api.main import create_app                    # noqa: E402
from core.config import settings                   # noqa: E402
from db.base import Base                           # noqa: E402
import db.models                                   # noqa: E402,F401

PASSWORD = "correct-horse-battery"
failures: list[str] = []


def safe(text) -> str:
    return str(text).encode("ascii", "replace").decode("ascii")


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"   {'OK  ' if ok else 'FAIL'} {label}" + (f"  [{safe(detail)}]" if detail else ""))
    if not ok:
        failures.append(label)


def build():
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

    app = create_app()
    app.dependency_overrides[get_db] = override
    return TestClient(app), Session, override


def main() -> int:
    chain = settings.provider_chain()
    print(f"\nProvider chain : {' -> '.join(chain) if chain else 'NONE'}")
    print(f"Memory enabled : {settings.memory_enabled}, "
          f"up to {settings.memory_max_items_in_context} per prompt")
    if not chain:
        print("\nPHASE 5 FAILED - no provider key set.\n")
        return 1

    client, Session, override = build()

    body = client.post(
        "/api/auth/register", json={"email": "owner@example.com", "password": PASSWORD}
    ).json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    workspace_id = client.post(
        "/api/workspaces", json={"name": "Research"}, headers=headers
    ).json()["id"]
    client.patch(
        f"/api/workspaces/{workspace_id}/settings",
        json={"temperature": 0.0, "max_tokens": 800, "model": "llama-3.3-70b-versatile"},
        headers=headers,
    )
    convo_base = f"/api/workspaces/{workspace_id}/conversations"
    memory_base = f"/api/workspaces/{workspace_id}/memory"

    print("\n1. SESSION ONE - the user states preferences in passing")
    first = client.post(convo_base, json={}, headers=headers).json()["id"]
    started = time.perf_counter()
    reply = client.post(
        f"{convo_base}/{first}/messages",
        json={"content": "Quick context before we start: I'm a backend engineer at a fintech "
                         "company, I always want answers in British English, and please keep "
                         "them under three sentences. What is a vector database?"},
        headers=headers,
    )
    check("HTTP 200", reply.status_code == 200, f"HTTP {reply.status_code}")
    if reply.status_code != 200:
        print(f"      {safe(reply.text[:300])}")
        return 1
    print(f"        turn took {time.perf_counter() - started:.1f}s "
          f"(includes a live extraction call)")

    print("\n2. The model decided what was worth remembering")
    remembered = client.get(memory_base, headers=headers).json()
    check("something was extracted", len(remembered) > 0, f"{len(remembered)} memories")
    for item in remembered:
        scope = "all workspaces" if item["workspace_id"] is None else "this workspace"
        print(f"        [{item['kind']:10}] {safe(item['content'])[:72]:74} "
              f"imp {item['importance']:.2f}  {scope}")

    joined = " ".join(m["content"].lower() for m in remembered)
    check("the language preference was captured",
          "british" in joined or "english" in joined, "looked for 'British English'")
    check("a durable fact was captured",
          any(word in joined for word in ["fintech", "backend", "engineer"]),
          "looked for the job context")

    print("\n3. Nothing trivial gets stored")
    before = len(client.get(memory_base, headers=headers).json())
    client.post(f"{convo_base}/{first}/messages", json={"content": "ok thanks"}, headers=headers)
    after = len(client.get(memory_base, headers=headers).json())
    check("'ok thanks' added no memories", after == before, f"{before} -> {after}")

    print("\n4. Ranking is importance x recency, not similarity")
    listed = client.get(memory_base, headers=headers).json()
    scores = [m["rank_score"] for m in listed]
    check("the list is ordered by rank", scores == sorted(scores, reverse=True), str(scores[:4]))
    in_context = [m for m in listed if m["in_context"]]
    check("some memories are marked in-context", len(in_context) > 0,
          f"{len(in_context)} of {len(listed)}")

    print("\n5. THE GATE: a new session, a new process, a question that never mentions it")
    restarted = create_app()
    restarted.dependency_overrides[get_db] = override

    with TestClient(restarted) as after_restart:
        second = after_restart.post(convo_base, json={}, headers=headers).json()["id"]
        started = time.perf_counter()
        answer = after_restart.post(
            f"{convo_base}/{second}/messages",
            json={"content": "How should I store embeddings?"},
            headers=headers,
        )
        check("HTTP 200", answer.status_code == 200, f"HTTP {answer.status_code}")
        if answer.status_code != 200:
            print(f"      {safe(answer.text[:300])}")
            return 1

        message = answer.json()["assistant_message"]
        used = message["memory_used"]
        check("memories were applied to the new conversation", len(used) > 0,
              f"{len(used)} applied")
        for item in used:
            print(f"        applied: {safe(item['content'])[:78]}")

        text = message["content"]
        print(f"\n        answer ({time.perf_counter() - started:.1f}s): {safe(text.strip())[:220]}")

        # The preference was "under three sentences". Behaviour is softer evidence than the
        # injection itself, so this is reported rather than gating the phase.
        sentences = len([s for s in text.replace("!", ".").replace("?", ".").split(".") if s.strip()])
        print(f"        sentence count: {sentences} (the stated preference was 'under three')")

        applied = " ".join(m["content"].lower() for m in used)
        check("the language preference reached the new session",
              "british" in applied or "english" in applied)

    print("\n6. The user is in control of what is remembered")
    target = client.get(memory_base, headers=headers).json()[0]
    pinned = client.patch(f"{memory_base}/{target['id']}", json={"is_pinned": True},
                          headers=headers).json()
    check("a memory can be pinned", pinned["is_pinned"] is True)
    edited = client.patch(f"{memory_base}/{target['id']}",
                          json={"content": "Corrected by the user"}, headers=headers).json()
    check("a memory can be corrected", edited["content"] == "Corrected by the user")
    check("a memory can be deleted",
          client.delete(f"{memory_base}/{target['id']}", headers=headers).status_code == 204)
    check("everything can be forgotten",
          client.delete(memory_base, headers=headers).status_code == 204)
    check("and it really is gone", client.get(memory_base, headers=headers).json() == [])

    print("\n7. Isolation")
    other = client.post(
        "/api/auth/register", json={"email": "other@example.com", "password": PASSWORD}
    ).json()
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}
    check("another user cannot read your memory",
          client.get(memory_base, headers=other_headers).status_code == 403)

    if failures:
        print(f"\nPHASE 5 FAILED - {len(failures)} problem(s):")
        for problem in failures:
            print(f"   - {problem}")
        return 1

    print("\nPHASE 5 PASSED - extracted live, ranked, injected across a restart, user-editable.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
