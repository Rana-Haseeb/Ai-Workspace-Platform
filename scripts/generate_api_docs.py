"""Generate ``docs/API.md`` from the live OpenAPI schema.

    python scripts/generate_api_docs.py
    python scripts/generate_api_docs.py --check    # fail if the committed file is stale

**Why generated rather than written.** Hand-written API documentation is wrong the moment
somebody adds a parameter, and nothing tells you. This reads the schema FastAPI builds from the
actual route signatures, so the document cannot describe an endpoint that does not exist or miss
one that does. ``--check`` runs in the Phase 10 gate, which is what stops the committed copy
drifting from the code.

Prose that a schema cannot express — what an endpoint is *for* — lives in ``NOTES`` below and is
merged in by path.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "docs" / "API.md"

METHODS = ("get", "post", "patch", "put", "delete")

TAG_ORDER = ["meta", "auth", "workspaces", "conversations", "documents", "memory",
             "skills", "dashboard"]

TAG_INTROS = {
    "meta": "Liveness. Deliberately reports no secrets and no connection string.",
    "auth": "Registration, login, logout and identity. A successful login sets an `HttpOnly` "
            "cookie **and** returns a bearer token, so a browser and an API client can both use "
            "the same endpoints.",
    "workspaces": "A workspace is the unit of isolation: it owns its conversations, documents "
                  "and assistant configuration. Every route below resolves ownership through "
                  "`get_owned_workspace`, so another user's id returns 403 rather than data.",
    "conversations": "Chat. `POST /messages` returns the complete reply; `POST /stream` returns "
                     "the same thing token by token as NDJSON.",
    "documents": "Upload, parse, embed and search. Ingestion runs in the background, so upload "
                 "returns immediately and the document reports `processing` until it is `ready`.",
    "memory": "What the assistant remembers about the user. Everything here is editable and "
              "deletable, because a memory that cannot be corrected silently shapes every "
              "future answer.",
    "skills": "Structured tasks — summarise, SWOT, meeting notes — and the versioned prompt "
              "library.",
    "dashboard": "Usage, cost and activity, aggregated in SQL rather than in Python.",
}

# Notes the schema genuinely cannot carry.
NOTES = {
    "/api/auth/login": "Rate limited to `AUTH_RATE_LIMIT_PER_MINUTE` (default 10/min per client). "
                       "Returns an identical 401 whether or not the account exists, so it cannot "
                       "be used to enumerate users.",
    "/api/auth/register": "Also rate limited at the auth budget.",
    "/api/workspaces/{workspace_id}/conversations/{conversation_id}/stream":
        "NDJSON, one JSON object per line — not SSE. SSE reconnects automatically, which for "
        "chat means silently re-sending a message the user already paid for. The first line is "
        "a `start` event carrying the citations, so sources render before the first token.",
    "/api/workspaces/{workspace_id}/documents":
        "`multipart/form-data`. Rejected on extension or on exceeding `MAX_UPLOAD_MB`. The "
        "stored filename is generated; the user's filename is metadata and never a path "
        "component.",
    "/api/workspaces/{workspace_id}/documents/search":
        "Hybrid by default: BM25 and vector rankings fused by Reciprocal Rank Fusion. Degrades "
        "to keyword-only if embeddings are unavailable, and says so in `mode` rather than "
        "quietly returning worse results.",
}


def anchor(text: str) -> str:
    return text.lower().replace(" ", "-").replace("/", "").replace("{", "").replace("}", "")


def render_params(operation: dict) -> str:
    rows = []
    for parameter in operation.get("parameters", []):
        schema = parameter.get("schema", {})
        kind = schema.get("type", schema.get("anyOf", [{}])[0].get("type", "—")
                          if schema.get("anyOf") else "—")
        rows.append(
            f"| `{parameter['name']}` | {parameter.get('in')} | "
            f"{'yes' if parameter.get('required') else 'no'} | {kind} | "
            f"{parameter.get('description', '').strip() or '—'} |"
        )
    if not rows:
        return ""
    return ("\n| Parameter | In | Required | Type | Description |\n"
            "|---|---|---|---|---|\n" + "\n".join(rows) + "\n")


def body_schema_name(operation: dict) -> str:
    content = operation.get("requestBody", {}).get("content", {})
    for media, spec in content.items():
        ref = spec.get("schema", {}).get("$ref", "")
        if ref:
            return ref.rsplit("/", 1)[-1]
        if media == "multipart/form-data":
            return "multipart/form-data"
    return ""


def build() -> str:
    from api.main import create_app

    schema = create_app().openapi()
    paths = schema["paths"]

    by_tag: dict[str, list[tuple[str, str, dict]]] = {}
    for path, operations in sorted(paths.items()):
        for method, operation in operations.items():
            if method not in METHODS:
                continue
            for tag in operation.get("tags", ["untagged"]):
                by_tag.setdefault(tag, []).append((method, path, operation))

    total = sum(len(v) for v in by_tag.values())
    ordered = [t for t in TAG_ORDER if t in by_tag] + \
              [t for t in sorted(by_tag) if t not in TAG_ORDER]

    lines: list[str] = [
        "# API Reference",
        "",
        "**Generated from the live OpenAPI schema — do not edit by hand.**",
        "",
        "```bash",
        "python scripts/generate_api_docs.py",
        "```",
        "",
        f"`{schema['info']['title']}` v{schema['info']['version']} — "
        f"**{total} operations** across {len(by_tag)} groups.",
        "",
        "An interactive version is served by the running application at "
        "[`/docs`](http://127.0.0.1:8000/docs), and the raw schema at `/openapi.json`.",
        "",
        "---",
        "",
        "## Conventions",
        "",
        "- **Base path** — every route is under `/api`.",
        "- **Authentication** — send `Authorization: Bearer <token>`, or rely on the `HttpOnly` "
        "cookie set at login. Unauthenticated requests to a protected route get **401**.",
        "- **Ownership** — a workspace belonging to another user returns **403**, never its "
        "contents. Identity always comes from the token; a `user_id` in a request body is "
        "ignored.",
        "- **Validation** — Pydantic rejects a malformed body with **422** and a field-level "
        "explanation.",
        "- **Rate limiting** — **429** with a `Retry-After` header. Two budgets: authentication "
        "and everything else.",
        "- **Errors** — a JSON object with a `detail` string.",
        "",
        "## Groups",
        "",
    ]
    for tag in ordered:
        lines.append(f"- [`{tag}`](#{anchor(tag)}) — {len(by_tag[tag])} operations")
    lines.append("")
    lines.append("---")
    lines.append("")

    for tag in ordered:
        lines.append(f"## {tag}")
        lines.append("")
        if tag in TAG_INTROS:
            lines.append(TAG_INTROS[tag])
            lines.append("")

        for method, path, operation in sorted(by_tag[tag], key=lambda x: (x[1], x[0])):
            summary = operation.get("summary") or ""
            lines.append(f"### `{method.upper()} {path}`")
            lines.append("")
            if summary:
                lines.append(f"**{summary}**")
                lines.append("")

            description = (operation.get("description") or "").strip()
            if description:
                lines.append(description)
                lines.append("")

            params = render_params(operation)
            if params:
                lines.append(params.strip())
                lines.append("")

            body = body_schema_name(operation)
            if body:
                lines.append(f"**Request body:** `{body}`")
                lines.append("")

            responses = operation.get("responses", {})
            codes = ", ".join(f"`{code}`" for code in sorted(responses))
            lines.append(f"**Responses:** {codes}")
            lines.append("")

            if path in NOTES:
                lines.append(f"> {NOTES[path]}")
                lines.append("")

        lines.append("---")
        lines.append("")

    schemas = schema.get("components", {}).get("schemas", {})
    lines.append("## Schemas")
    lines.append("")
    lines.append(f"{len(schemas)} models, all generated from the Pydantic definitions in "
                 f"`schemas/`.")
    lines.append("")
    lines.append("| Model | Fields |")
    lines.append("|---|---|")
    for name in sorted(schemas):
        fields = list(schemas[name].get("properties", {}))
        shown = ", ".join(f"`{f}`" for f in fields[:8])
        if len(fields) > 8:
            shown += f", … (+{len(fields) - 8})"
        lines.append(f"| **{name}** | {shown or '—'} |")
    lines.append("")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="exit non-zero if the committed file is out of date")
    args = parser.parse_args()

    generated = build()

    if args.check:
        if not OUT.exists():
            print(f"FAIL {OUT.relative_to(ROOT)} does not exist. Run without --check.")
            return 1
        if OUT.read_text(encoding="utf-8") != generated:
            print(f"FAIL {OUT.relative_to(ROOT)} is stale — the API changed. Regenerate it.")
            return 1
        print(f"OK   {OUT.relative_to(ROOT)} matches the live schema.")
        return 0

    OUT.write_text(generated, encoding="utf-8")
    print(f"Written -> {OUT.relative_to(ROOT)} ({len(generated.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
