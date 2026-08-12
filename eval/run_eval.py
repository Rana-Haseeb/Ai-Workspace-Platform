"""Run the evaluation dataset against the real platform.

    python eval/run_eval.py                 # everything
    python eval/run_eval.py --category doc  # one category
    python eval/run_eval.py --limit 5       # a quick smoke run

Scenarios go through the **HTTP API**, not the services directly. That is deliberate: it means
the numbers describe the platform a user actually talks to — routing, ownership checks,
retrieval, memory injection and persistence all included — rather than a library called under
laboratory conditions.

Writes ``eval/results.json``.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
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
from eval import metrics                           # noqa: E402
from eval.dataset import (                         # noqa: E402
    SCENARIOS, SEED_MEMORIES, SEED_PROMPTS, Scenario, corpus_files,
)
from eval.metrics import ScenarioResult            # noqa: E402
import db.models                                   # noqa: E402,F401

PASSWORD = "correct-horse-battery"


def safe(text) -> str:
    return str(text).encode("ascii", "replace").decode("ascii")


class Harness:
    """A throwaway platform instance, seeded and ready to answer."""

    def __init__(self, model: str | None = None):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)

        def override():
            session = self.Session()
            try:
                yield session
            finally:
                session.close()

        conversations_router.SessionLocal = self.Session
        documents_router.SessionLocal = self.Session

        app = create_app()
        app.dependency_overrides[get_db] = override
        self.client = TestClient(app)

        body = self.client.post(
            "/api/auth/register", json={"email": "eval@example.com", "password": PASSWORD}
        ).json()
        self.headers = {"Authorization": f"Bearer {body['access_token']}"}
        self.workspace_id = self.client.post(
            "/api/workspaces", json={"name": "Evaluation"}, headers=self.headers
        ).json()["id"]
        self.base = f"/api/workspaces/{self.workspace_id}"

        self.client.patch(
            f"{self.base}/settings",
            json={
                "temperature": 0.0,           # deterministic, so a re-run is comparable
                "max_tokens": 1024,
                "model": model or "llama-3.3-70b-versatile",
                "system_prompt": "You are a precise assistant. Answer from the material you are "
                                 "given. If it does not contain the answer, say so plainly.",
            },
            headers=self.headers,
        )
        self._prompt_ids: dict[str, int] = {}
        self._conversations: dict[str, int] = {}

    # ------------------------------------------------------------------- setup
    def ingest_corpus(self) -> int:
        chunks = 0
        for path in corpus_files():
            self.client.post(
                f"{self.base}/documents",
                files={"file": (path.name, path.read_bytes(), "text/markdown")},
                headers=self.headers,
            )
        for document in self.client.get(f"{self.base}/documents", headers=self.headers).json():
            chunks += document["chunk_count"]
        return chunks

    def seed_memories(self) -> int:
        for kind, content, importance in SEED_MEMORIES:
            self.client.post(
                f"{self.base}/memory",
                json={"content": content, "kind": kind, "importance": importance,
                      "workspace_scoped": False},
                headers=self.headers,
            )
        return len(SEED_MEMORIES)

    def seed_prompts(self) -> int:
        for title, body, category in SEED_PROMPTS:
            created = self.client.post(
                f"{self.base}/prompts",
                json={"title": title, "body": body, "category": category},
                headers=self.headers,
            ).json()
            self._prompt_ids[title] = created["id"]
        return len(SEED_PROMPTS)

    # --------------------------------------------------------------- execution
    def _conversation_for(self, scenario: Scenario) -> int:
        """A fresh conversation, unless the scenario continues an earlier one."""
        key = scenario.continues or scenario.id
        if key not in self._conversations:
            self._conversations[key] = self.client.post(
                f"{self.base}/conversations", json={}, headers=self.headers
            ).json()["id"]
        return self._conversations[key]

    def run(self, scenario: Scenario) -> ScenarioResult:
        started = time.perf_counter()
        try:
            if scenario.skill:
                response = self.client.post(
                    f"{self.base}/skills/{scenario.skill}/run",
                    json={"input": scenario.prompt}, headers=self.headers,
                )
                if response.status_code != 200:
                    raise RuntimeError(f"HTTP {response.status_code}: {response.text[:120]}")
                body = response.json()
                answer, citations, memory_used = body["output"], body["citations"], []
                structured = body.get("structured")
            else:
                text = scenario.prompt
                if scenario.prompt_template:
                    template = self.client.post(
                        f"{self.base}/prompts/{self._prompt_ids[scenario.prompt_template]}/use",
                        headers=self.headers,
                    ).json()
                    text = template["body"].replace("{input}", scenario.prompt)

                response = self.client.post(
                    f"{self.base}/conversations/{self._conversation_for(scenario)}/messages",
                    json={"content": text}, headers=self.headers,
                )
                if response.status_code != 200:
                    raise RuntimeError(f"HTTP {response.status_code}: {response.text[:120]}")
                message = response.json()["assistant_message"]
                answer = message["content"]
                citations = message["citations"]
                memory_used = message["memory_used"]
                structured = None
        except Exception as error:  # noqa: BLE001
            return ScenarioResult(
                scenario_id=scenario.id, category=scenario.category, passed=False, score=0.0,
                latency_ms=int((time.perf_counter() - started) * 1000), error=str(error)[:200],
            )

        latency_ms = int((time.perf_counter() - started) * 1000)
        return self._score(scenario, answer, citations, memory_used, structured, latency_ms)

    # ----------------------------------------------------------------- scoring
    def _score(self, scenario, answer, citations, memory_used, structured, latency_ms):
        checks: dict[str, bool] = {}
        scores: list[float] = []

        def record(name: str, result: tuple[bool, float]) -> None:
            ok, score = result
            checks[name] = ok
            scores.append(score)

        if scenario.expect_all:
            record("expect_all", metrics.contains_all(answer, scenario.expect_all))
        if scenario.expect_any:
            record("expect_any", metrics.contains_any(answer, scenario.expect_any))
        if scenario.expect_none:
            record("expect_none", metrics.contains_none(answer, scenario.expect_none))
        if scenario.expect_ignorance:
            record("admits_ignorance", metrics.admits_ignorance(answer))
        if scenario.cite_document:
            ok, score = metrics.cites_document(citations, scenario.cite_document)
            checks["cites_right_document"] = ok
            scores.append(score)
            checks["_citation_score"] = score          # feeds the citation-quality metric
        if scenario.require_inline_citation:
            record("inline_citation", metrics.has_inline_citation(answer))
        if scenario.recall_memory:
            record("recalled_memory", metrics.recalled_memory(memory_used, scenario.recall_memory))
        if scenario.max_sentences:
            record("respected_length", metrics.within_sentences(answer, scenario.max_sentences))
        if scenario.structured_fields:
            record("structured_fields",
                   metrics.structured_has_fields(structured, scenario.structured_fields))

        if not scores:                                  # e.g. edge-04, which only must not crash
            checks["produced_output"] = bool(answer.strip())
            scores.append(1.0 if answer.strip() else 0.0)

        real_checks = {k: v for k, v in checks.items() if not k.startswith("_")}
        return ScenarioResult(
            scenario_id=scenario.id, category=scenario.category,
            passed=all(real_checks.values()),
            score=round(sum(scores) / len(scores), 3),
            latency_ms=latency_ms, checks=checks, answer=answer[:400],
            citations=citations[:3], memory_used=memory_used[:3],
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", help="Run one category only")
    parser.add_argument("--limit", type=int, help="Run only the first N scenarios")
    parser.add_argument("--model", help="Override the model")
    parser.add_argument("--out", default=str(Path(__file__).parent / "results.json"))
    args = parser.parse_args()

    if not settings.provider_chain():
        print("\nNo provider key configured. Set GROQ_API_KEY in .env.\n")
        return 1

    scenarios = SCENARIOS
    if args.category:
        scenarios = [s for s in scenarios if s.category == args.category]
    if args.limit:
        scenarios = scenarios[: args.limit]

    print(f"\nEvaluation — {len(scenarios)} scenarios")
    print(f"Provider chain : {' -> '.join(settings.provider_chain())}")

    harness = Harness(model=args.model)
    print(f"Model          : {args.model or 'llama-3.3-70b-versatile'}")
    print("\nSeeding…")
    chunks = harness.ingest_corpus()
    memories = harness.seed_memories()
    prompts = harness.seed_prompts()
    print(f"   {len(corpus_files())} documents, {chunks} chunks, {memories} memories, "
          f"{prompts} prompt templates")

    print("\nRunning:")
    results: list[ScenarioResult] = []
    started = time.perf_counter()
    current_category = None
    for scenario in scenarios:
        if scenario.category != current_category:
            current_category = scenario.category
            print(f"\n  {current_category.upper()}")
        result = harness.run(scenario)
        results.append(result)
        mark = "PASS" if result.passed else "FAIL"
        detail = f"{result.score:.2f}  {result.latency_ms:>5}ms"
        if result.error:
            detail += f"  ERROR {safe(result.error)[:60]}"
        elif not result.passed:
            missed = [k for k, v in result.checks.items() if not v and not k.startswith("_")]
            detail += f"  missed: {','.join(missed)}"
        print(f"    {mark}  {scenario.id:10} {detail}")

    elapsed = time.perf_counter() - started
    summary = metrics.summarise(results)

    print("\n" + "=" * 66)
    print("RESULTS")
    print("=" * 66)
    print(f"  Scenarios          {summary['scenarios']}")
    print(f"  Accuracy           {summary['accuracy']:.1%}")
    print(f"  Task success       {summary['task_success']:.1%}   (partial credit)")
    print(f"  Memory recall      {summary['memory_recall']:.1%}" if summary["memory_recall"]
          is not None else "  Memory recall      n/a")
    print(f"  Citation quality   {summary['citation_quality']:.1%}"
          if summary["citation_quality"] is not None else "  Citation quality   n/a")
    print(f"  Mean response      {summary['mean_response_time_ms']}ms")
    print(f"  p95 response       {summary['p95_response_time_ms']}ms")
    print(f"  Errors             {summary['errors']}")
    print(f"  Wall clock         {elapsed:.1f}s")

    print("\n  By category:")
    for category, bucket in summary["by_category"].items():
        print(f"    {category:14} {bucket['passed']:>2}/{bucket['total']:<2} "
              f"accuracy {bucket['accuracy']:.0%}  mean score {bucket['mean_score']:.2f}")

    if summary["failed_scenarios"]:
        print(f"\n  Failed: {', '.join(summary['failed_scenarios'])}")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": args.model or "llama-3.3-70b-versatile",
        "provider_chain": settings.provider_chain(),
        "temperature": 0.0,
        "wall_clock_seconds": round(elapsed, 1),
        "summary": summary,
        "scenarios": [
            {
                "id": r.scenario_id, "category": r.category, "passed": r.passed,
                "score": r.score, "latency_ms": r.latency_ms,
                "checks": {k: v for k, v in r.checks.items() if not k.startswith("_")},
                "answer": r.answer, "error": r.error,
                "citations": [c.get("filename") for c in r.citations],
                "memory_used": [m.get("content") for m in r.memory_used],
            }
            for r in results
        ],
    }
    Path(args.out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\n  Written to {Path(args.out).relative_to(ROOT)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
