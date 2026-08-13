"""Populate a running instance with realistic content, for screenshots and demos.

    python scripts/seed_demo.py                       # against http://127.0.0.1:8000
    python scripts/seed_demo.py --reset               # delete the demo user's workspaces first

Empty screens photograph badly and demo worse: a dashboard reading zero proves nothing, and a
memory page with one row does not show what the feature is for. This creates a workspace with
documents, conversations, memory, prompts and usage history, so every screen has something real
on it.

**Everything here is genuine.** Documents are really parsed, chunked and embedded; conversations
are really answered by the model; memory is really extracted. Nothing is inserted directly into
the database to make a screen look fuller than the platform can actually make it.

Requires the API to be running.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import urllib.error                                  # noqa: E402
import urllib.request                                # noqa: E402
import json as json_module                           # noqa: E402

EMAIL = "demo@example.com"
PASSWORD = "correct-horse-battery"
BASE = "http://127.0.0.1:8000/api"

DOCUMENTS = {
    "vector_database_benchmark.md": """# Vector Database Benchmark — Q1 2026

## Summary

We evaluated four vector stores against our production workload: 2.4 million embeddings at
768 dimensions, with a p95 latency target of 50 milliseconds.

## Results

| Store | p50 latency | p95 latency | Recall@10 | Ops burden (1-10) |
|---|---|---|---|---|
| Qdrant | 9 ms | 21 ms | 0.97 | 6 |
| pgvector (HNSW) | 14 ms | 33 ms | 0.95 | 9 |
| Weaviate | 11 ms | 28 ms | 0.96 | 6 |
| Milvus | 8 ms | 19 ms | 0.97 | 4 |

## Decision

We chose **pgvector**, despite it being the second slowest. The operations team scored it 9 out
of 10 for maintenance burden because it needs no new service, no new backup story and no new
on-call rotation. We traded roughly 5 milliseconds of median latency for one fewer system to run.

Milvus scored best on raw performance and worst on operational cost — it would have meant a
dedicated cluster for a workload our existing Postgres handles.

## Follow-up

Re-evaluate at 10 million embeddings. pgvector's HNSW index build time grows faster than the
alternatives, and the rebuild currently locks the table.
""",
    "incident_2026_02_14.md": """# Incident Report — Search Outage, 14 February 2026

## Impact

Search was unavailable for **47 minutes**, affecting approximately **2,300 users**. No data was
lost. Write traffic was unaffected throughout.

## Timeline

- **09:14** — A scheduled index rebuild began on the embeddings table.
- **09:16** — Search latency rose from 14 ms to over 30 seconds.
- **09:41** — First customer report. Automated alerting had not fired.
- **09:52** — Cause identified as the index rebuild holding an exclusive lock.
- **10:01** — Rebuild cancelled; search recovered immediately.

## Why detection was slow

The health check queried a different table from the one being rebuilt, so it kept returning
healthy while user-facing search was completely blocked. The check confirmed the database was
reachable, not that search worked.

## Actions

| Action | Owner | Status |
|---|---|---|
| Move index rebuilds to `CREATE INDEX CONCURRENTLY` | Marcus | In progress |
| Health check must run the real search query | Priya | Done |
| Alert on p95 latency, not just availability | Marcus | Open |
""",
    "onboarding_policy.md": """# Engineering Onboarding Policy

## First week

New engineers receive a laptop, accounts, and a **£400 desk setup budget** to spend as they like.
A named onboarding buddy is assigned before the start date, not after.

## Production access

Production database access requires **30 days** of tenure and a completed security review. This
applies to everyone regardless of seniority.

**Interns do not receive production database access at any point.** They work against a seeded
staging copy, which is refreshed weekly.

## First contribution

The expectation is a merged pull request in the first week. It is deliberately allowed to be
trivial — a typo fix counts. The point is to exercise the whole pipeline early, while somebody
is still sitting with you.
""",
}

CONVERSATIONS = [
    ("Which vector database did we pick?", [
        "According to our benchmark, which vector database did we choose and what did we give up?",
        "What score did the operations team give it for maintenance burden?",
    ]),
    ("February search outage", [
        "How long did the February search outage last and how many users were affected?",
        "Why was detection so slow?",
    ]),
    ("Onboarding questions", [
        "How long before a new engineer can get production database access?",
    ]),
]

MEMORY_SEED = (
    "A few things about me so you don't have to ask again: I'm a backend engineer working "
    "mostly on PostgreSQL-heavy systems, I prefer British English, and I like answers kept to "
    "two or three sentences unless I ask for detail."
)

PROMPTS = [
    ("Risk review", "List the three biggest risks in the following, most serious first:\n\n{input}",
     "business"),
    ("Explain simply", "Explain the following to a new engineer in plain terms:\n\n{input}",
     "education"),
    # Category is a closed set in schemas/prompt.py — "engineering" is rejected with a 422.
    ("Incident summary", "Summarise this incident: impact, cause, and the single most important "
                         "follow-up action.\n\n{input}", "research"),
]


def call(method: str, path: str, token: str | None = None, payload=None, raw=None,
         content_type="application/json"):
    url = f"{BASE}{path}"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if raw is not None:
        data = raw
        headers["Content-Type"] = content_type
    elif payload is not None:
        data = json_module.dumps(payload).encode()
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = response.read()
            return response.status, (json_module.loads(body) if body else None)
    except urllib.error.HTTPError as error:
        body = error.read().decode()
        return error.code, body[:200]


def upload(token: str, workspace: int, filename: str, text: str):
    """multipart/form-data by hand — no new dependency for one call."""
    boundary = "----demoseed7f3a2b"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: text/markdown\r\n\r\n"
    ).encode() + text.encode() + f"\r\n--{boundary}--\r\n".encode()

    return call("POST", f"/workspaces/{workspace}/documents", token, raw=body,
                content_type=f"multipart/form-data; boundary={boundary}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true",
                        help="delete the demo user's existing workspaces first")
    args = parser.parse_args()

    print(f"\nSeeding {BASE}\n")

    status, _ = call("GET", "/health")
    if status != 200:
        print("The API is not running. Start it first:\n"
              "  python -m uvicorn api.main:app --reload\n")
        return 1

    call("POST", "/auth/register", payload={"name": "Demo User", "email": EMAIL,
                                            "password": PASSWORD})
    status, body = call("POST", "/auth/login", payload={"email": EMAIL, "password": PASSWORD})
    if status != 200:
        print(f"Could not log in: {status} {body}")
        return 1
    token = body["access_token"]
    print(f"  signed in as {EMAIL}")

    if args.reset:
        _, existing = call("GET", "/workspaces", token)
        # Prompts and memory hang off the USER, not the workspace — `prompt_templates` and
        # `memory_items` both carry user_id with a nullable workspace_id, so deleting a workspace
        # leaves them behind. Missing that produced a prompt library full of duplicates on the
        # second run, which is the schema working as designed and the reset not accounting for it.
        for workspace in existing or []:
            wsid = workspace["id"]
            _, prompts = call("GET", f"/workspaces/{wsid}/prompts", token)
            for prompt in prompts or []:
                call("DELETE", f"/workspaces/{wsid}/prompts/{prompt['id']}", token)
            call("DELETE", f"/workspaces/{wsid}", token)
        print(f"  removed {len(existing or [])} existing workspace(s) and their prompts")

    status, workspace = call("POST", "/workspaces", token, {
        "name": "Platform Research",
        "description": "Vector databases, incidents, and how we onboard engineers.",
        "icon": "flask",
    })
    if status != 201:
        print(f"Could not create the workspace: {status} {workspace}")
        return 1
    wid = workspace["id"]
    print(f"  workspace {wid}: {workspace['name']}")

    call("PATCH", f"/workspaces/{wid}/settings", token, {
        "assistant_name": "Research assistant",
        "role": "Infrastructure research analyst",
        "system_prompt": "Answer from the workspace documents where they cover the question, and "
                         "cite them. Be precise with figures.",
        "personality": "professional",
        "response_style": "balanced",
    })

    # ---------------------------------------------------------------------- documents
    print("\n  documents")
    for filename, text in DOCUMENTS.items():
        status, _ = upload(token, wid, filename, text)
        print(f"    {'ok  ' if status in (200, 201) else 'FAIL'} {filename}")

    for _ in range(60):
        _, listed = call("GET", f"/workspaces/{wid}/documents", token)
        if listed and all(d["status"] in ("ready", "failed") for d in listed):
            break
        time.sleep(1)
    _, listed = call("GET", f"/workspaces/{wid}/documents", token)
    for document in listed or []:
        print(f"    {document['filename']}: {document['status']}, "
              f"{document.get('chunk_count', 0)} chunks")

    # ------------------------------------------------------------------------- memory
    print("\n  memory")
    status, conversation = call("POST", f"/workspaces/{wid}/conversations", token, {})
    call("POST", f"/workspaces/{wid}/conversations/{conversation['id']}/messages", token,
         {"content": MEMORY_SEED})
    time.sleep(2)
    _, memories = call("GET", f"/workspaces/{wid}/memory", token)
    print(f"    extracted {len(memories or [])} memories from one message")

    # ------------------------------------------------------------------ conversations
    print("\n  conversations")
    for title, questions in CONVERSATIONS:
        _, conversation = call("POST", f"/workspaces/{wid}/conversations", token, {})
        for question in questions:
            status, _ = call(
                "POST", f"/workspaces/{wid}/conversations/{conversation['id']}/messages",
                token, {"content": question})
            if status != 200:
                print(f"    FAIL {question[:40]}")
        print(f"    {title} ({len(questions)} turns)")

    # ----------------------------------------------------------------------- prompts
    print("\n  prompts")
    for title, body_text, category in PROMPTS:
        call("POST", f"/workspaces/{wid}/prompts", token,
             {"title": title, "body": body_text, "category": category})
    # Edit one, so the version history has something in it.
    _, prompts = call("GET", f"/workspaces/{wid}/prompts", token)
    if prompts:
        first = prompts[0]
        call("PATCH", f"/workspaces/{wid}/prompts/{first['id']}", token,
             {"title": first["title"],
              "body": first["body"] + "\n\nRank each risk as high, medium or low.",
              "category": first.get("category", "business")})
        print(f"    {len(prompts)} prompts, '{first['title']}' edited to version 2")

    # The dashboard nests its figures under `totals` and `usage` rather than returning them flat.
    _, dashboard = call("GET", f"/workspaces/{wid}/dashboard", token)
    totals = (dashboard or {}).get("totals", {})
    usage = (dashboard or {}).get("usage", {})
    print(f"\n  dashboard: {totals.get('conversations')} conversations, "
          f"{totals.get('messages')} messages, {totals.get('documents')} documents, "
          f"{totals.get('memories')} memories, {usage.get('tokens_total')} tokens")

    print(f"\nDone. Sign in at http://localhost:5173 with {EMAIL} / {PASSWORD}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
