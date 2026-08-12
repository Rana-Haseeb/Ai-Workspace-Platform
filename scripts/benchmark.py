"""Performance measurements for ``docs/PERFORMANCE.md``.

Eight measurements, each repeated and reported as a distribution rather than a single number.
A single timing is an anecdote: the first call in a process pays import costs, the first query
pays connection setup, and a mean over three runs hides both.

    python scripts/benchmark.py               # everything
    python scripts/benchmark.py --offline     # skip the ones that call a provider

**Warm-up is discarded, and that is not cheating — it is the difference between measuring the
application and measuring Python's import machinery.** Phase 3 recorded a 20.7 s chat response
that was 18 s of ``langchain_openai`` importing; the deployment now pays that at boot. Every
measurement below therefore runs a discarded warm-up pass first, and says so.

Writes ``docs/performance.json``.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient           # noqa: E402
from sqlalchemy import create_engine                # noqa: E402
from sqlalchemy.orm import sessionmaker             # noqa: E402
from sqlalchemy.pool import StaticPool              # noqa: E402

from core.config import settings                    # noqa: E402
from core.security import create_access_token, hash_password, verify_password  # noqa: E402
from db.base import Base                            # noqa: E402
import db.models                                    # noqa: F401,E402

OUT = ROOT / "docs" / "performance.json"
PASSWORD = "correct-horse-battery"

results: dict = {}


def safe(text) -> str:
    return str(text).encode("ascii", "replace").decode("ascii")


def measure(label: str, fn, repeats: int = 20, warmup: int = 2, unit: str = "ms") -> dict:
    """Time ``fn`` and report the distribution. Warm-up runs are executed and discarded."""
    for _ in range(warmup):
        fn()

    samples: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - started) * 1000)

    samples.sort()
    row = {
        "unit": unit,
        "runs": repeats,
        "min": round(samples[0], 2),
        "p50": round(statistics.median(samples), 2),
        "p95": round(samples[min(int(len(samples) * 0.95), len(samples) - 1)], 2),
        "max": round(samples[-1], 2),
        "mean": round(statistics.fmean(samples), 2),
    }
    print(f"   {label:<44} p50 {row['p50']:>9.2f}  p95 {row['p95']:>9.2f}  "
          f"min {row['min']:>8.2f}  max {row['max']:>9.2f}  (n={repeats})")
    results[label] = row
    return row


# --------------------------------------------------------------------------- fixtures
def build_app():
    """A real application on an in-memory database, wired exactly as the tests wire it."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    from api.deps import get_db
    from api.main import create_app
    import api.routers.conversations as conversations_router
    import api.routers.documents as documents_router

    conversations_router.SessionLocal = Session
    documents_router.SessionLocal = Session

    # The limiter would refuse a benchmark that fires hundreds of requests, so it is switched
    # off here. That is measuring the application, not the throttle in front of it.
    settings.rate_limit_per_minute = 0
    settings.auth_rate_limit_per_minute = 0

    app = create_app()

    def override():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override
    client = TestClient(app)
    return client, Session


def seed(client) -> dict:
    """A user with a workspace, a conversation and some history to query over."""
    email = f"bench-{int(time.time() * 1000)}@example.com"
    client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    login = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    workspace = client.post("/api/workspaces", json={"name": "Benchmark"},
                            headers=headers).json()
    return {"headers": headers, "workspace": workspace["id"]}


# ------------------------------------------------------------------------ measurements
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true",
                        help="skip measurements that call a provider")
    parser.add_argument("--live-only", action="store_true",
                        help="only the provider measurements, merged into the existing file")
    args = parser.parse_args()

    # The provider sections are metered per minute on the free tier, so they are re-runnable on
    # their own. Merging rather than overwriting keeps the local numbers from the earlier run —
    # the same lesson as experiments/run_experiments.py.
    if args.live_only and OUT.exists():
        results.update(json.loads(OUT.read_text(encoding="utf-8")).get("measurements", {}))

    print("\nPerformance benchmark")
    print(f"Database : {'SQLite (in-memory)' if settings.is_sqlite() else 'PostgreSQL'}")
    print(f"Provider : {' -> '.join(settings.provider_chain()) or 'none'}\n")

    client, Session = build_app()
    context = seed(client)
    headers, workspace_id = context["headers"], context["workspace"]

    if args.live_only:
        return live_measurements(finish=True)

    # ---------------------------------------------------------------- 1. API round trip
    print("1. HTTP round trip (no model, no embedding)")
    measure("health probe", lambda: client.get("/api/health"))
    measure("authenticated list (workspaces)",
            lambda: client.get("/api/workspaces", headers=headers))
    measure("workspace detail + settings",
            lambda: client.get(f"/api/workspaces/{workspace_id}", headers=headers))

    # ------------------------------------------------------------------ 2. authentication
    print("\n2. Authentication")
    # Deliberately expensive: argon2id is tuned so that guessing is slow. A fast number here
    # would be a finding, not a win.
    measure("argon2id hash", lambda: hash_password(PASSWORD), repeats=10)
    digest = hash_password(PASSWORD)
    measure("argon2id verify", lambda: verify_password(PASSWORD, digest), repeats=10)
    measure("issue a JWT", lambda: create_access_token(1), repeats=50)

    # ---------------------------------------------------------------------- 3. database
    print("\n3. Database")
    from db.models import Conversation, Message
    session = Session()
    conversation = Conversation(workspace_id=workspace_id, title="Benchmark",
                                session_id="benchmark-session")
    session.add(conversation)
    session.commit()
    for index in range(200):
        session.add(Message(conversation_id=conversation.id,
                            role="user" if index % 2 == 0 else "assistant",
                            content=f"message number {index} about vector databases",
                            tokens_in=10, tokens_out=20, latency_ms=100))
    session.commit()
    session.close()

    def read_transcript():
        s = Session()
        try:
            s.query(Message).filter(Message.conversation_id == conversation.id).all()
        finally:
            s.close()

    measure("read a 200-message transcript", read_transcript)
    measure("dashboard aggregate (HTTP)",
            lambda: client.get(f"/api/workspaces/{workspace_id}/dashboard", headers=headers))

    # ------------------------------------------------------------------ 4. text processing
    print("\n4. Document processing (local stages)")
    from services import document_service

    corpus = (ROOT / "eval" / "corpus" / "vector_databases.md").read_text(encoding="utf-8")
    big_path = ROOT / "data" / "_benchmark_input.md"
    big_path.parent.mkdir(exist_ok=True)
    big_path.write_text(corpus * 20, encoding="utf-8")   # ~40 KB, a realistic report
    size_kb = big_path.stat().st_size // 1024

    measure(f"extract text from {size_kb} KB",
            lambda: document_service.extract_pages(big_path, ".md"), repeats=10)
    pages = document_service.extract_pages(big_path, ".md")
    measure(f"chunk {size_kb} KB at {settings.chunk_size} chars",
            lambda: document_service.chunk_pages(pages), repeats=10)

    parsed_chunks = document_service.chunk_pages(pages)
    big_path.unlink(missing_ok=True)
    print(f"   (produced {len(parsed_chunks)} chunks)")

    # ----------------------------------------------------------------------- 5. retrieval
    print("\n5. Retrieval")
    from db.models import Chunk as ChunkRow, Document
    from services import retrieval_service

    # Real rows in a real table, because BM25 here reads from the database — timing a list
    # comprehension in memory would not be measuring what production does.
    session = Session()
    document = Document(workspace_id=workspace_id, filename="benchmark.md",
                        stored_path=str(big_path), mime_type="text/markdown",
                        size_bytes=size_kb * 1024, page_count=len(pages), status="ready")
    session.add(document)
    session.commit()
    for chunk in parsed_chunks:
        session.add(ChunkRow(document_id=document.id, ordinal=chunk.ordinal, text=chunk.text,
                             page=chunk.page, char_start=chunk.char_start,
                             char_end=chunk.char_end))
    session.commit()
    total_chunks = session.query(ChunkRow).count()
    session.close()
    print(f"   (corpus in the database: {total_chunks} chunks)")

    original_mode = settings.retrieval_mode
    settings.retrieval_mode = "bm25"
    try:
        def bm25_search():
            s = Session()
            try:
                retrieval_service.retrieve(s, workspace_id, "how fast was pgvector with hnsw")
            finally:
                s.close()

        measure(f"BM25 retrieval over {total_chunks} chunks", bm25_search, repeats=20)
    finally:
        settings.retrieval_mode = original_mode

    # ---------------------------------------------------------------------- 6. memory
    print("\n6. Memory ranking")
    from datetime import timedelta
    from db.models import MemoryItem
    from services import memory_service

    now = datetime.now(timezone.utc)
    items = [
        MemoryItem(user_id=1, workspace_id=workspace_id, kind="fact",
                   content=f"remembered fact {i}", importance=0.5 + (i % 5) / 10,
                   created_at=now - timedelta(days=i % 40))
        for i in range(500)
    ]
    measure("rank 500 memories by importance x recency",
            lambda: sorted(items, key=lambda m: memory_service.rank_score(m, now), reverse=True),
            repeats=20)

    if args.offline:
        print("\n(skipping provider measurements: --offline)")
    else:
        live_measurements(finish=False)

    return write_results()


def live_measurements(finish: bool) -> int:
    """The two measurements that call a provider.

    Sample counts are small on purpose: the free embedding tier is metered per minute, and a
    benchmark that exhausts the allowance measures the retry backoff instead of the service.
    A small n is stated in the report rather than padded.
    """
    # --------------------------------------------------------------------- 7. embeddings
    print("\n7. Embeddings (live provider)")
    from services import embedding_service
    try:
        measure(f"embed one query ({settings.embedding_provider}, {settings.embedding_dim}d)",
                lambda: embedding_service.embed_query("how fast was pgvector"),
                repeats=3, warmup=1)
    except Exception as error:  # noqa: BLE001
        print(f"   SKIPPED - {safe(error)[:100]}")
        results[f"embed one query ({settings.embedding_provider})"] = {
            "error": safe(error)[:160]}

    # -------------------------------------------------------------------------- 8. chat
    print("\n8. Chat completion (live provider)")
    from services.llm_service import get_llm
    try:
        llm = get_llm()

        def one_turn():
            llm.chat([("system", "Answer in one short sentence."),
                      ("user", "What is a vector database?")])

        one_turn()      # warm-up, and it populates last_used_model for the label
        measure(f"model round trip ({llm.last_used_model} via {llm.last_used_provider})",
                one_turn, repeats=3, warmup=0)
    except Exception as error:  # noqa: BLE001
        print(f"   SKIPPED - {safe(error)[:100]}")
        results["model round trip"] = {"error": safe(error)[:160]}

    return write_results() if finish else 0


def write_results() -> int:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "database": "sqlite-memory" if settings.is_sqlite() else "postgresql",
        "provider_chain": settings.provider_chain(),
        "chunk_size": settings.chunk_size,
        "embedding_dim": settings.embedding_dim,
        "note": "Warm-up runs are executed and discarded; see the module docstring.",
        "measurements": results,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nWritten to {OUT.relative_to(ROOT)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
