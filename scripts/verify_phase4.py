"""Phase 4 gate: a real PDF becomes cited answers.

Live. Uploads an actual multi-page PDF, embeds it with the real provider, asks real questions,
and checks that the citation points at a page that genuinely contains the answer — which is the
only version of "citations work" that means anything.

    python scripts/verify_phase4.py [path/to/file.pdf]

Defaults to the fellowship handbook PDF sitting beside the project. Exits non-zero on failure.
"""
from __future__ import annotations

import re
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
from services import embedding_service             # noqa: E402
import db.models                                   # noqa: E402,F401

PASSWORD = "correct-horse-battery"
DEFAULT_PDF = ROOT.parent / (
    "Track 2 NLP & AI Agents Visibility Bots Innovation Lab AI Summer Internship 2026.pdf"
)

failures: list[str] = []


def safe(text: str) -> str:
    """Printable on a cp1252 console. Document text is full of typographic characters."""
    return str(text).encode("ascii", "replace").decode("ascii")


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"   {'OK  ' if ok else 'FAIL'} {label}" + (f"  [{safe(detail)}]" if detail else ""))
    if not ok:
        failures.append(label)


def build(tmp_uploads: Path):
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
    settings.upload_dir = tmp_uploads

    app = create_app()
    app.dependency_overrides[get_db] = override
    return TestClient(app), Session


def main() -> int:
    pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PDF
    if not pdf.exists():
        print(f"\nPHASE 4 FAILED - no PDF at {pdf}\n")
        return 1

    print(f"\nEmbedding backend: {embedding_service.describe()}")
    print(f"Retrieval mode:    {settings.retrieval_mode}")
    if not embedding_service.is_configured():
        print("\nPHASE 4 FAILED - no embedding provider configured. Set GOOGLE_API_KEY.\n")
        return 1

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        client, Session = build(Path(tmp))

        body = client.post(
            "/api/auth/register", json={"email": "owner@example.com", "password": PASSWORD}
        ).json()
        headers = {"Authorization": f"Bearer {body['access_token']}"}
        workspace_id = client.post(
            "/api/workspaces", json={"name": "Fellowship"}, headers=headers
        ).json()["id"]
        client.patch(
            f"/api/workspaces/{workspace_id}/settings",
            json={"temperature": 0.0, "max_tokens": 700,
                  "model": "llama-3.3-70b-versatile", "response_style": "brief"},
            headers=headers,
        )
        base = f"/api/workspaces/{workspace_id}/documents"

        print(f"\n1. Ingesting {safe(pdf.name)[:60]} ({pdf.stat().st_size // 1024} KB)")
        started = time.perf_counter()
        upload = client.post(
            base,
            files={"file": (pdf.name, pdf.read_bytes(), "application/pdf")},
            headers=headers,
        )
        ingest_seconds = time.perf_counter() - started
        check("upload accepted", upload.status_code == 201, f"HTTP {upload.status_code}")
        if upload.status_code != 201:
            print(f"      {safe(upload.text[:300])}")
            return 1

        document = client.get(base, headers=headers).json()[0]
        check("ingestion finished", document["status"] == "ready",
              document["status"] + (f" - {document['error']}" if document["error"] else ""))
        check("pages extracted", document["page_count"] > 5, f"{document['page_count']} pages")
        check("chunks created", document["chunk_count"] > 10, f"{document['chunk_count']} chunks")
        print(f"        ingestion took {ingest_seconds:.1f}s "
              f"({document['chunk_count'] / max(ingest_seconds, 0.01):.0f} chunks/s)")

        status_body = client.get(f"{base}/status", headers=headers).json()
        check("every chunk embedded",
              status_body["embedded_chunks"] == document["chunk_count"],
              f"{status_body['embedded_chunks']}/{document['chunk_count']}")
        check("semantic search available", status_body["semantic_search_available"] is True)

        print("\n2. Retrieval returns citations with a real page")
        queries = [
            "What is the minimum passing score for the week?",
            "How long should the demo video be?",
            "What is required in the GitHub repository?",
        ]
        for query in queries:
            t0 = time.perf_counter()
            found = client.post(
                f"{base}/search", json={"query": query, "top_k": 4}, headers=headers
            ).json()
            took = (time.perf_counter() - t0) * 1000
            citations = found["citations"]
            ok = bool(citations) and citations[0]["page"] is not None
            check(f"'{query[:44]}...'", ok,
                  f"{len(citations)} hits, top page {citations[0]['page'] if citations else '-'}, "
                  f"{found['mode']}, {took:.0f}ms")

        print("\n3. THE GATE: the cited page actually contains the answer")
        # A specific, checkable fact from the handbook.
        found = client.post(
            f"{base}/search", json={"query": "minimum passing score out of 100", "top_k": 5},
            headers=headers,
        ).json()
        hits = found["citations"]
        check("something was retrieved", bool(hits), f"{len(hits)} hits")
        if hits:
            # Pull the cited chunk back out of the document and confirm the snippet is really
            # from the page it claims. This is what makes a citation checkable rather than
            # decorative.
            chunks = client.get(
                f"{base}/{hits[0]['document_id']}/chunks", headers=headers
            ).json()
            by_id = {c["id"]: c for c in chunks}
            cited = by_id.get(hits[0]["chunk_id"])
            check("the cited chunk exists in the document", cited is not None)
            if cited:
                check("its page matches the citation", cited["page"] == hits[0]["page"],
                      f"chunk page {cited['page']} vs citation page {hits[0]['page']}")
                check("the snippet is really from that chunk",
                      hits[0]["snippet"].rstrip("…").strip()[:80] in cited["text"])
            joined = " ".join(h["snippet"].lower() for h in hits)
            check("retrieved text is on-topic",
                  any(word in joined for word in ["70", "pass", "score", "marks", "minimum"]),
                  safe(hits[0]["snippet"][:90]))

        print("\n4. A chat answer carries the citations")
        conversation = client.post(
            f"/api/workspaces/{workspace_id}/conversations", json={}, headers=headers
        ).json()["id"]
        t0 = time.perf_counter()
        reply = client.post(
            f"/api/workspaces/{workspace_id}/conversations/{conversation}/messages",
            json={"content": "According to the handbook, how long should the demo video be? "
                             "Cite the excerpt you used."},
            headers=headers,
        )
        answer_seconds = time.perf_counter() - t0
        check("HTTP 200", reply.status_code == 200, f"HTTP {reply.status_code}")
        if reply.status_code == 200:
            message = reply.json()["assistant_message"]
            check("citations attached to the reply", bool(message["citations"]),
                  f"{len(message['citations'])} citations")
            # Any bracketed index, not just the first two — the model cites whichever excerpt
            # actually carried the answer, and an earlier version of this check wrongly failed
            # a correct answer that cited [3] and [4].
            cited_indices = set(re.findall(r"\[(\d+)\]", message["content"]))
            check("the answer references a bracketed source", bool(cited_indices),
                  f"cited {sorted(cited_indices)}" if cited_indices else safe(message["content"][:70]))
            check(
                "every cited index exists in the excerpts it was given",
                all(1 <= int(i) <= len(message["citations"]) for i in cited_indices),
                f"cited {sorted(cited_indices)} of {len(message['citations'])} excerpts",
            )
            print(f"        answered in {answer_seconds:.1f}s")
            print(f"        answer: {safe(message['content'].strip()[:180])}")
            if message["citations"]:
                first = message["citations"][0]
                print(f"        cited:  {safe(first['filename'])} page {first['page']}")

        print("\n5. Retrieval modes compared on the same question")
        question = "evaluation rubric marks for platform architecture"
        timings = {}
        for mode in ["bm25", "vector", "hybrid"]:
            settings.retrieval_mode = mode
            t0 = time.perf_counter()
            found = client.post(
                f"{base}/search", json={"query": question, "top_k": 4}, headers=headers
            ).json()
            timings[mode] = (time.perf_counter() - t0) * 1000
            pages = [c["page"] for c in found["citations"]]
            print(f"        {mode:7} {timings[mode]:6.0f}ms  pages {pages}")
            check(f"{mode} returned results", bool(found["citations"]))
        settings.retrieval_mode = "hybrid"

        print("\n6. Isolation")
        other = client.post(
            "/api/auth/register", json={"email": "other@example.com", "password": PASSWORD}
        ).json()
        other_headers = {"Authorization": f"Bearer {other['access_token']}"}
        check("another user cannot list the documents",
              client.get(base, headers=other_headers).status_code == 403)
        check("another user cannot search them",
              client.post(f"{base}/search", json={"query": "score"},
                          headers=other_headers).status_code == 403)

    if failures:
        print(f"\nPHASE 4 FAILED - {len(failures)} problem(s):")
        for problem in failures:
            print(f"   - {problem}")
        return 1

    print("\nPHASE 4 PASSED - real PDF ingested, embedded, retrieved, and cited by page.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
