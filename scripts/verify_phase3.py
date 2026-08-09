"""Phase 3 gate: chat works, persists, and streams — against a real model.

Unlike the earlier gates this one makes live provider calls, because the thing being verified is
that a real reply arrives, gets stored, and is still there afterwards. The test suite stays
offline and fast by using a stub; this script is where the real network is exercised.

    python scripts/verify_phase3.py

Needs a provider key in .env. Exits non-zero on any failure.
"""
from __future__ import annotations

import json
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
from api.deps import get_db                        # noqa: E402
from api.main import create_app                    # noqa: E402
from core.config import settings                   # noqa: E402
from db.base import Base                           # noqa: E402
import db.models                                   # noqa: E402,F401

PASSWORD = "correct-horse-battery"
failures: list[str] = []


def safe(text: str) -> str:
    """Make model output printable on a Windows cp1252 console.

    Models emit typographic characters — non-breaking hyphens, em dashes, smart quotes — and the
    default Windows console encoding cannot represent them. Without this, a successful call is
    reported as a crash by the code that prints the result.
    """
    return text.encode("ascii", "replace").decode("ascii")


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

    # The streaming route opens its own session; point it at this database too.
    conversations_router.SessionLocal = Session

    app = create_app()
    app.dependency_overrides[get_db] = override
    return TestClient(app), Session, engine, override


def main() -> int:
    chain = settings.provider_chain()
    print(f"\nProvider chain: {' -> '.join(chain) if chain else 'NONE CONFIGURED'}")
    if not chain:
        print("\nPHASE 3 FAILED - no provider key set. Put GROQ_API_KEY in .env.\n")
        return 1

    client, Session, engine, override = build()

    body = client.post(
        "/api/auth/register", json={"email": "owner@example.com", "password": PASSWORD}
    ).json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    workspace_id = client.post(
        "/api/workspaces", json={"name": "Research"}, headers=headers
    ).json()["id"]
    # Deterministic replies make the recall check below meaningful rather than lucky.
    client.patch(
        f"/api/workspaces/{workspace_id}/settings",
        json={"temperature": 0.0, "max_tokens": 512, "response_style": "brief"},
        headers=headers,
    )
    base = f"/api/workspaces/{workspace_id}/conversations"

    print("\n1. A real reply arrives")
    conversation_id = client.post(base, json={}, headers=headers).json()["id"]
    started = time.perf_counter()
    reply = client.post(
        f"{base}/{conversation_id}/messages",
        json={"content": "In one short sentence, what is a vector database?"},
        headers=headers,
    )
    elapsed = time.perf_counter() - started
    check("HTTP 200", reply.status_code == 200, f"HTTP {reply.status_code}")
    if reply.status_code != 200:
        print(f"      {reply.text[:400]}")
        print("\nPHASE 3 FAILED - the model call did not succeed.\n")
        return 1

    answer = reply.json()["assistant_message"]
    check("reply is not empty", len(answer["content"].strip()) > 0,
          f"{len(answer['content'])} chars")
    check("model recorded", bool(answer["model"]), str(answer["model"]))
    check("latency recorded", answer["latency_ms"] > 0, f"{answer['latency_ms']}ms")
    check("tokens recorded", answer["tokens_out"] > 0, f"~{answer['tokens_out']} out")
    print(f"        round trip: {elapsed:.2f}s")
    print(f"        answer: {safe(answer['content'].strip()[:150])}")

    print("\n2. A title was generated from the first message")
    title = reply.json()["title"]
    check("title is not the placeholder", title != "New conversation", title)
    check("title is short", len(title) <= 200, f"{len(title)} chars")

    print("\n3. The model actually receives the history")
    client.post(f"{base}/{conversation_id}/messages",
                json={"content": "My favourite colour is teal. Remember it."}, headers=headers)
    recall = client.post(
        f"{base}/{conversation_id}/messages",
        json={"content": "What colour did I just tell you? Reply with the colour only."},
        headers=headers,
    ).json()["assistant_message"]["content"]
    check("earlier turn is recalled", "teal" in recall.lower(), recall.strip()[:80])

    print("\n4. Streaming delivers more than one chunk")
    stream_conversation = client.post(base, json={}, headers=headers).json()["id"]
    events: list[dict] = []
    first_token_at = None
    stream_started = time.perf_counter()
    with client.stream(
        "POST",
        f"{base}/{stream_conversation}/stream",
        json={"content": "Count from one to eight in words, separated by commas."},
        headers=headers,
    ) as response:
        for line in response.iter_lines():
            if not line.strip():
                continue
            event = json.loads(line)
            if event["type"] == "token" and first_token_at is None:
                first_token_at = time.perf_counter() - stream_started
            events.append(event)

    kinds = [e["type"] for e in events]
    tokens = [e["text"] for e in events if e["type"] == "token"]
    check("stream opens with start", kinds[0] == "start" if kinds else False)
    check("stream ends with done", kinds[-1] == "done" if kinds else False,
          kinds[-1] if kinds else "no events")
    check("more than one chunk", len(tokens) > 1, f"{len(tokens)} chunks")
    if first_token_at:
        print(f"        time to first token: {first_token_at:.2f}s")
        print(f"        total: {time.perf_counter() - stream_started:.2f}s")
    print(f"        streamed: {safe(''.join(tokens).strip()[:120])}")

    print("\n5. The streamed reply was persisted")
    transcript = client.get(f"{base}/{stream_conversation}", headers=headers).json()
    check("both sides stored", len(transcript["messages"]) == 2,
          f"{len(transcript['messages'])} messages")
    check(
        "stored text matches what was streamed",
        transcript["messages"][-1]["content"].strip() == "".join(tokens).strip(),
    )

    print("\n6. Search finds it")
    found = client.get(f"{base}?q=teal", headers=headers).json()
    check("search matches a message body", any(c["id"] == conversation_id for c in found),
          f"{len(found)} results")

    print("\n7. THE GATE: history survives a restart")
    restarted = create_app()
    restarted.dependency_overrides[get_db] = override
    with TestClient(restarted) as after:
        detail = after.get(f"{base}/{conversation_id}", headers=headers).json()
        check("transcript intact", len(detail["messages"]) == 6,
              f"{len(detail['messages'])} messages")
        check("title intact", detail["title"] == title, detail["title"])
        again = after.get(f"{base}?q=teal", headers=headers).json()
        check("search still works", len(again) > 0, f"{len(again)} results")

    print("\n8. Usage was logged for the dashboard")
    session = Session()
    from db.models import Log

    entries = session.query(Log).filter_by(event="chat", status="ok").all()
    check("one log row per reply", len(entries) >= 4, f"{len(entries)} rows")
    check("tokens attributed", all(e.tokens_out > 0 for e in entries))
    total_in = sum(e.tokens_in for e in entries)
    total_out = sum(e.tokens_out for e in entries)
    print(f"        ~{total_in} tokens in, ~{total_out} out across {len(entries)} calls")
    session.close()

    if failures:
        print(f"\nPHASE 3 FAILED - {len(failures)} problem(s):")
        for problem in failures:
            print(f"   - {problem}")
        return 1

    print("\nPHASE 3 PASSED - live replies, titling, history, streaming, search, persistence.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
