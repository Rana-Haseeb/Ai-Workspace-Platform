"""Phase 6 gate: every registered skill produces real output, and prompts version properly.

Live. Runs every skill in the registry against a real model — including the structured ones,
where the model has to return a valid nested schema rather than prose.

    python scripts/verify_phase6.py

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
from skills import registry                        # noqa: E402
import db.models                                   # noqa: E402,F401

PASSWORD = "correct-horse-battery"
failures: list[str] = []

# One input per skill, chosen so the output is judgeable rather than generic.
INPUTS = {
    "summarize": "The board met on Tuesday. Revenue rose 12% to 4.2M, driven by the enterprise "
                 "tier. Churn is up slightly at 3.1%. Maria will present a retention plan by "
                 "the 30th. The Berlin office decision was deferred to next quarter.",
    "research": "What is the minimum passing score?",
    "meeting_notes": "Standup notes: Ali said the migration is blocked on the schema review. "
                     "Sara will review it by Thursday. We agreed to ship the beta on the 14th "
                     "regardless. Someone should tell support - nobody volunteered. Open: do we "
                     "need a rollback plan?",
    "task_planner": "Migrate our product search from Elasticsearch to pgvector.",
    "swot": "Launching a paid tier for our open-source developer tool.",
    "report": "Our Q3 retention dropped from 94% to 89%.",
    "email": "Tell my client the API integration will slip by one week because of an upstream "
             "vendor outage.",
    "code_review": "def get_user(uid):\n    q = \"SELECT * FROM users WHERE id = \" + uid\n"
                   "    return db.execute(q).fetchone()",
    "ideas": "Ways to reduce drop-off during developer onboarding.",
}


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
    return TestClient(app)


def main() -> int:
    if not settings.provider_chain():
        print("\nPHASE 6 FAILED - no provider key set.\n")
        return 1

    client = build()
    body = client.post(
        "/api/auth/register", json={"email": "owner@example.com", "password": PASSWORD}
    ).json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    workspace_id = client.post(
        "/api/workspaces", json={"name": "Work"}, headers=headers
    ).json()["id"]
    client.patch(
        f"/api/workspaces/{workspace_id}/settings",
        json={"temperature": 0.1, "max_tokens": 2048, "model": "llama-3.3-70b-versatile"},
        headers=headers,
    )
    base = f"/api/workspaces/{workspace_id}"

    print(f"\n1. The registry holds {len(registry.SKILLS)} skills")
    check("at least six, as required", len(registry.SKILLS) >= 6, f"{len(registry.SKILLS)}")
    listed = client.get(f"{base}/skills", headers=headers).json()
    check("the API lists all of them", len(listed) == len(registry.SKILLS))
    check("no emoji icons", all(s["icon"].isascii() for s in listed))

    print("\n2. THE GATE: every skill runs against a real model")
    total_ms = 0
    for skill in registry.all_skills():
        user_input = INPUTS.get(skill.slug, "Something worth thinking about carefully.")
        started = time.perf_counter()
        response = client.post(
            f"{base}/skills/{skill.slug}/run", json={"input": user_input}, headers=headers
        )
        elapsed = (time.perf_counter() - started) * 1000
        total_ms += elapsed

        if response.status_code != 200:
            check(f"{skill.slug}", False, f"HTTP {response.status_code} {response.text[:90]}")
            continue

        result = response.json()
        output = (result["output"] or "").strip()
        ok = len(output) > 40
        shape = "structured" if skill.output_schema else "text"
        if skill.output_schema is not None and not result["structured"]:
            ok = False
            shape = "structured BUT EMPTY"

        check(f"{skill.slug:14} {shape:12}", ok, f"{len(output):>5} chars, {elapsed:>6.0f}ms")
        if ok:
            first = output.replace("\n", " ")[:100]
            print(f"          {safe(first)}")

    print(f"\n        total {total_ms / 1000:.1f}s for {len(registry.SKILLS)} skills")

    print("\n3. Structured skills return real structure, not prose in a box")
    swot = client.post(f"{base}/skills/swot/run",
                       json={"input": "Launching a paid tier."}, headers=headers).json()
    structured = swot.get("structured") or {}
    for field in ["strengths", "weaknesses", "opportunities", "threats"]:
        value = structured.get(field)
        check(f"swot.{field} is a populated list",
              isinstance(value, list) and len(value) > 0,
              f"{len(value) if isinstance(value, list) else type(value).__name__} items")

    plan = client.post(f"{base}/skills/task_planner/run",
                       json={"input": INPUTS['task_planner']}, headers=headers).json()
    steps = (plan.get("structured") or {}).get("steps") or []
    check("task_planner returned ordered steps", len(steps) >= 3, f"{len(steps)} steps")
    if steps:
        check("each step has an estimate and a dependency",
              all("estimate" in s and "blocked_by" in s for s in steps))
        print(f"          first: {safe(steps[0].get('step', ''))[:80]}")

    print("\n4. Usage is counted")
    listed = client.get(f"{base}/skills", headers=headers).json()
    ran = [s for s in listed if s["use_count"] > 0]
    check("every run was counted", len(ran) == len(registry.SKILLS),
          f"{len(ran)}/{len(registry.SKILLS)} skills have a count")

    print("\n5. Prompts version instead of overwriting")
    prompts = f"{base}/prompts"
    v1 = client.post(prompts, json={"title": "Bug report", "body": "Describe the bug: {details}",
                                    "category": "programming"}, headers=headers).json()
    v2 = client.patch(f"{prompts}/{v1['id']}",
                      json={"body": "Describe the bug, then the expected behaviour: {details}"},
                      headers=headers).json()
    check("editing made a new row", v2["id"] != v1["id"], f"{v1['id']} -> {v2['id']}")
    check("version incremented", v2["version"] == 2)
    check("it points at its parent", v2["parent_id"] == v1["id"])

    history = client.get(f"{prompts}/{v2['id']}/history", headers=headers).json()
    check("history has both versions", [h["version"] for h in history] == [1, 2])
    check("the original text survives", history[0]["body"] == "Describe the bug: {details}")

    listed_prompts = client.get(prompts, headers=headers).json()
    check("only the current version is listed", len(listed_prompts) == 1,
          f"{len(listed_prompts)} listed")

    print("\n6. Isolation")
    other = client.post(
        "/api/auth/register", json={"email": "other@example.com", "password": PASSWORD}
    ).json()
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}
    check("another user cannot run skills here",
          client.post(f"{base}/skills/summarize/run", json={"input": "x"},
                      headers=other_headers).status_code == 403)
    check("another user cannot read the prompts",
          client.get(prompts, headers=other_headers).status_code == 403)

    if failures:
        print(f"\nPHASE 6 FAILED - {len(failures)} problem(s):")
        for problem in failures:
            print(f"   - {problem}")
        return 1

    print(f"\nPHASE 6 PASSED - {len(registry.SKILLS)} skills ran live, prompts version cleanly.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
