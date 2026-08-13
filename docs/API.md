# API Reference

**Generated from the live OpenAPI schema — do not edit by hand.**

```bash
python scripts/generate_api_docs.py
```

`AI Workspace Platform` v0.1.0 — **43 operations** across 8 groups.

An interactive version is served by the running application at [`/docs`](http://127.0.0.1:8000/docs), and the raw schema at `/openapi.json`.

---

## Conventions

- **Base path** — every route is under `/api`.
- **Authentication** — send `Authorization: Bearer <token>`, or rely on the `HttpOnly` cookie set at login. Unauthenticated requests to a protected route get **401**.
- **Ownership** — a workspace belonging to another user returns **403**, never its contents. Identity always comes from the token; a `user_id` in a request body is ignored.
- **Validation** — Pydantic rejects a malformed body with **422** and a field-level explanation.
- **Rate limiting** — **429** with a `Retry-After` header. Two budgets: authentication and everything else.
- **Errors** — a JSON object with a `detail` string.

## Groups

- [`meta`](#meta) — 1 operations
- [`auth`](#auth) — 4 operations
- [`workspaces`](#workspaces) — 8 operations
- [`conversations`](#conversations) — 8 operations
- [`documents`](#documents) — 6 operations
- [`memory`](#memory) — 6 operations
- [`skills`](#skills) — 8 operations
- [`dashboard`](#dashboard) — 2 operations

---

## meta

Liveness. Deliberately reports no secrets and no connection string.

### `GET /api/health`

**Health**

Liveness probe. Deliberately reports no secrets and no connection strings.

**Responses:** `200`

---

## auth

Registration, login, logout and identity. A successful login sets an `HttpOnly` cookie **and** returns a bearer token, so a browser and an API client can both use the same endpoints.

### `POST /api/auth/login`

**Login**

**Request body:** `LoginRequest`

**Responses:** `200`, `422`

> Rate limited to `AUTH_RATE_LIMIT_PER_MINUTE` (default 10/min per client). Returns an identical 401 whether or not the account exists, so it cannot be used to enumerate users.

### `POST /api/auth/logout`

**Logout**

Clear the session cookie.

A signed JWT cannot be revoked server-side without a denylist, so a token already copied out
of the browser stays valid until it expires. Clearing the cookie is what logout means here,
and the short expiry is what bounds the rest. The security review says so explicitly rather
than implying logout does more than it does.

**Responses:** `204`

### `GET /api/auth/me`

**Me**

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Responses:** `200`, `422`

### `POST /api/auth/register`

**Register**

**Request body:** `RegisterRequest`

**Responses:** `201`, `422`

> Also rate limited at the auth budget.

---

## workspaces

A workspace is the unit of isolation: it owns its conversations, documents and assistant configuration. Every route below resolves ownership through `get_owned_workspace`, so another user's id returns 403 rather than data.

### `GET /api/workspaces`

**List Workspaces**

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Responses:** `200`, `422`

### `POST /api/workspaces`

**Create Workspace**

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Request body:** `WorkspaceCreate`

**Responses:** `201`, `422`

### `GET /api/workspaces/meta`

**Workspace Metadata**

Choices the settings and create screens offer.

Served from the backend so the picker cannot drift from what the server will accept — the
frontend renders whatever this returns rather than keeping its own copy of the list.

**Responses:** `200`

### `DELETE /api/workspaces/{workspace_id}`

**Delete Workspace**

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Responses:** `204`, `422`

### `GET /api/workspaces/{workspace_id}`

**Get Workspace**

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Responses:** `200`, `422`

### `PATCH /api/workspaces/{workspace_id}`

**Update Workspace**

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Request body:** `WorkspaceUpdate`

**Responses:** `200`, `422`

### `GET /api/workspaces/{workspace_id}/settings`

**Get Settings**

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Responses:** `200`, `422`

### `PATCH /api/workspaces/{workspace_id}/settings`

**Update Settings**

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Request body:** `AssistantSettingsUpdate`

**Responses:** `200`, `422`

---

## conversations

Chat. `POST /messages` returns the complete reply; `POST /stream` returns the same thing token by token as NDJSON.

### `GET /api/workspaces/{workspace_id}/conversations`

**List Conversations**

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `workspace_id` | path | yes | integer | — |
| `q` | query | no | string | Search titles and message bodies |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Responses:** `200`, `422`

### `POST /api/workspaces/{workspace_id}/conversations`

**Create Conversation**

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Request body:** `ConversationCreate`

**Responses:** `201`, `422`

### `DELETE /api/workspaces/{workspace_id}/conversations/{conversation_id}`

**Delete Conversation**

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `conversation_id` | path | yes | integer | — |
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Responses:** `204`, `422`

### `GET /api/workspaces/{workspace_id}/conversations/{conversation_id}`

**Get Conversation**

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `conversation_id` | path | yes | integer | — |
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Responses:** `200`, `422`

### `PATCH /api/workspaces/{workspace_id}/conversations/{conversation_id}`

**Update Conversation**

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `conversation_id` | path | yes | integer | — |
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Request body:** `ConversationUpdate`

**Responses:** `200`, `422`

### `POST /api/workspaces/{workspace_id}/conversations/{conversation_id}/messages`

**Send Message**

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `conversation_id` | path | yes | integer | — |
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Request body:** `ChatRequest`

**Responses:** `200`, `422`

### `PATCH /api/workspaces/{workspace_id}/conversations/{conversation_id}/messages/{message_id}/pin`

**Toggle Pin**

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `conversation_id` | path | yes | integer | — |
| `message_id` | path | yes | integer | — |
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Responses:** `200`, `422`

### `POST /api/workspaces/{workspace_id}/conversations/{conversation_id}/stream`

**Stream Message**

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `conversation_id` | path | yes | integer | — |
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Request body:** `ChatRequest`

**Responses:** `200`, `422`

> NDJSON, one JSON object per line — not SSE. SSE reconnects automatically, which for chat means silently re-sending a message the user already paid for. The first line is a `start` event carrying the citations, so sources render before the first token.

---

## documents

Upload, parse, embed and search. Ingestion runs in the background, so upload returns immediately and the document reports `processing` until it is `ready`.

### `GET /api/workspaces/{workspace_id}/documents`

**List Documents**

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Responses:** `200`, `422`

> `multipart/form-data`. Rejected on extension or on exceeding `MAX_UPLOAD_MB`. The stored filename is generated; the user's filename is metadata and never a path component.

### `POST /api/workspaces/{workspace_id}/documents`

**Upload Document**

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Request body:** `Body_upload_document_api_workspaces__workspace_id__documents_post`

**Responses:** `201`, `422`

> `multipart/form-data`. Rejected on extension or on exceeding `MAX_UPLOAD_MB`. The stored filename is generated; the user's filename is metadata and never a path component.

### `POST /api/workspaces/{workspace_id}/documents/search`

**Search Documents**

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Request body:** `SearchRequest`

**Responses:** `200`, `422`

> Hybrid by default: BM25 and vector rankings fused by Reciprocal Rank Fusion. Degrades to keyword-only if embeddings are unavailable, and says so in `mode` rather than quietly returning worse results.

### `GET /api/workspaces/{workspace_id}/documents/status`

**Knowledge Base Status**

What this workspace's knowledge base can actually do right now.

The UI uses this to say "keyword search only" out loud rather than quietly returning worse
results when embeddings are unavailable.

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Responses:** `200`, `422`

### `DELETE /api/workspaces/{workspace_id}/documents/{document_id}`

**Delete Document**

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `document_id` | path | yes | integer | — |
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Responses:** `204`, `422`

### `GET /api/workspaces/{workspace_id}/documents/{document_id}/chunks`

**Document Chunks**

Every chunk of one document, in order. This is what a citation chip opens.

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `document_id` | path | yes | integer | — |
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Responses:** `200`, `422`

---

## memory

What the assistant remembers about the user. Everything here is editable and deletable, because a memory that cannot be corrected silently shapes every future answer.

### `DELETE /api/workspaces/{workspace_id}/memory`

**Forget Everything**

Delete every memory visible in this workspace, including the user-wide ones.

A single, obvious way to make the assistant forget. Anything less than "all of it" is a
privacy control people cannot reason about.

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Responses:** `204`, `422`

### `GET /api/workspaces/{workspace_id}/memory`

**List Memories**

Everything remembered here, ordered exactly as it would be injected.

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Responses:** `200`, `422`

### `POST /api/workspaces/{workspace_id}/memory`

**Create Memory**

Add a memory by hand, rather than waiting for the extractor to notice it.

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Request body:** `MemoryCreate`

**Responses:** `201`, `422`

### `GET /api/workspaces/{workspace_id}/memory/status`

**Memory Status**

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Responses:** `200`, `422`

### `DELETE /api/workspaces/{workspace_id}/memory/{memory_id}`

**Delete Memory**

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `memory_id` | path | yes | integer | — |
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Responses:** `204`, `422`

### `PATCH /api/workspaces/{workspace_id}/memory/{memory_id}`

**Update Memory**

Correct, re-weight, or pin a memory.

Correcting matters: the extractor is a language model reading conversation, so it will
occasionally record something subtly wrong. A memory that cannot be fixed is worse than no
memory, because it silently shapes every future answer.

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `memory_id` | path | yes | integer | — |
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Request body:** `MemoryUpdate`

**Responses:** `200`, `422`

---

## skills

Structured tasks — summarise, SWOT, meeting notes — and the versioned prompt library.

### `GET /api/workspaces/{workspace_id}/prompts`

**List Prompts**

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `workspace_id` | path | yes | integer | — |
| `category` | query | no | string | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Responses:** `200`, `422`

### `POST /api/workspaces/{workspace_id}/prompts`

**Create Prompt**

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Request body:** `PromptCreate`

**Responses:** `201`, `422`

### `DELETE /api/workspaces/{workspace_id}/prompts/{prompt_id}`

**Delete Prompt**

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `prompt_id` | path | yes | integer | — |
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Responses:** `204`, `422`

### `PATCH /api/workspaces/{workspace_id}/prompts/{prompt_id}`

**Edit Prompt**

Editing returns the **new** version. The row you sent is retired, not changed.

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `prompt_id` | path | yes | integer | — |
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Request body:** `PromptUpdate`

**Responses:** `200`, `422`

### `GET /api/workspaces/{workspace_id}/prompts/{prompt_id}/history`

**Prompt History**

Every version, oldest first — what this prompt used to say.

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `prompt_id` | path | yes | integer | — |
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Responses:** `200`, `422`

### `POST /api/workspaces/{workspace_id}/prompts/{prompt_id}/use`

**Use Prompt**

Record that a prompt was used, and hand back its text.

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `prompt_id` | path | yes | integer | — |
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Responses:** `200`, `422`

### `GET /api/workspaces/{workspace_id}/skills`

**List Skills**

Every registered skill, with how often it has been run.

Definitions come from the code registry rather than the database, so a newly added skill is
available the moment the server restarts — no migration, no manual insert.

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Responses:** `200`, `422`

### `POST /api/workspaces/{workspace_id}/skills/{slug}/run`

**Run Skill**

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `slug` | path | yes | string | — |
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Request body:** `SkillRunRequest`

**Responses:** `200`, `422`

---

## dashboard

Usage, cost and activity, aggregated in SQL rather than in Python.

### `GET /api/workspaces/{workspace_id}/conversations/{conversation_id}/export`

**Export Conversation**

One conversation as Markdown.

``download=false`` returns it inline, which is what the print view renders for PDF.
``download=true`` sets a Content-Disposition header so the browser saves a .md file.

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `conversation_id` | path | yes | integer | — |
| `workspace_id` | path | yes | integer | — |
| `download` | query | no | boolean | Send as a file attachment |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Responses:** `200`, `422`

### `GET /api/workspaces/{workspace_id}/dashboard`

**Dashboard**

Every figure here is a live aggregate, not a stored counter.

| Parameter | In | Required | Type | Description |
|---|---|---|---|---|
| `workspace_id` | path | yes | integer | — |
| `authorization` | header | no | string | — |
| `aiw_access` | cookie | no | string | — |

**Responses:** `200`, `422`

---

## Schemas

43 models, all generated from the Pydantic definitions in `schemas/`.

| Model | Fields |
|---|---|
| **ActivityEntry** | `event`, `detail`, `model`, `tokens`, `latency_ms`, `status`, `created_at` |
| **AssistantSettingsResponse** | `assistant_name`, `role`, `system_prompt`, `model`, `temperature`, `max_tokens`, `personality`, `response_style`, … (+2) |
| **AssistantSettingsUpdate** | `assistant_name`, `role`, `system_prompt`, `model`, `temperature`, `max_tokens`, `personality`, `response_style`, … (+2) |
| **AuthResponse** | `user`, `access_token`, `token_type` |
| **Body_upload_document_api_workspaces__workspace_id__documents_post** | `file` |
| **ChatRequest** | `content` |
| **ChatResponse** | `user_message`, `assistant_message`, `conversation_id`, `title` |
| **ChunkResponse** | `id`, `ordinal`, `text`, `page` |
| **CitationResponse** | `chunk_id`, `document_id`, `filename`, `page`, `snippet`, `score` |
| **ConversationCreate** | `title` |
| **ConversationDetail** | `id`, `title`, `session_id`, `is_pinned`, `tags`, `created_at`, `updated_at`, `message_count`, … (+2) |
| **ConversationResponse** | `id`, `title`, `session_id`, `is_pinned`, `tags`, `created_at`, `updated_at`, `message_count`, … (+1) |
| **ConversationUpdate** | `title`, `is_pinned`, `tags` |
| **DailyUsage** | `date`, `tokens` |
| **DashboardResponse** | `totals`, `usage`, `by_event`, `daily`, `activity`, `top_memories`, `provider_chain` |
| **DocumentResponse** | `id`, `filename`, `mime_type`, `size_bytes`, `page_count`, `chunk_count`, `status`, `error`, … (+1) |
| **EventUsage** | `event`, `calls`, `tokens` |
| **HTTPValidationError** | `detail` |
| **KnowledgeBaseStatus** | `documents`, `chunks`, `embedded_chunks`, `embedding_backend`, `retrieval_mode`, `semantic_search_available` |
| **LoginRequest** | `email`, `password` |
| **MemoryCreate** | `content`, `kind`, `importance`, `workspace_scoped` |
| **MemoryResponse** | `id`, `kind`, `content`, `importance`, `is_pinned`, `workspace_id`, `use_count`, `last_used_at`, … (+3) |
| **MemoryStatus** | `total`, `pinned`, `in_context`, `by_kind`, `enabled`, `max_in_context` |
| **MemoryUpdate** | `content`, `kind`, `importance`, `is_pinned` |
| **MessageResponse** | `id`, `role`, `content`, `citations`, `memory_used`, `is_pinned`, `model`, `tokens_in`, … (+4) |
| **PromptCreate** | `title`, `body`, `category`, `workspace_scoped` |
| **PromptResponse** | `id`, `title`, `body`, `category`, `version`, `parent_id`, `is_current`, `use_count`, … (+2) |
| **PromptUpdate** | `title`, `body`, `category` |
| **RegisterRequest** | `email`, `password`, `display_name` |
| **SearchRequest** | `query`, `top_k` |
| **SearchResponse** | `query`, `mode`, `citations`, `took_ms`, `vector_error` |
| **SkillRunRequest** | `input`, `conversation_id` |
| **SkillRunResponse** | `slug`, `message_id`, `output`, `structured`, `citations`, `model`, `tokens_in`, `tokens_out`, … (+1) |
| **SkillSummary** | `slug`, `name`, `category`, `description`, `icon`, `input_label`, `input_placeholder`, `uses_documents`, … (+3) |
| **TopMemory** | `content`, `kind`, `use_count` |
| **UsageTotals** | `calls`, `failed_calls`, `tokens_in`, `tokens_out`, `tokens_total`, `estimated_cost_usd`, `average_latency_ms`, `p95_latency_ms` |
| **UserResponse** | `id`, `email`, `display_name`, `created_at` |
| **ValidationError** | `loc`, `msg`, `type`, `input`, `ctx` |
| **WorkspaceCreate** | `name`, `description`, `icon` |
| **WorkspaceDetail** | `id`, `name`, `description`, `icon`, `created_at`, `settings` |
| **WorkspaceResponse** | `id`, `name`, `description`, `icon`, `created_at` |
| **WorkspaceTotals** | `conversations`, `messages`, `documents`, `chunks`, `memories`, `prompts` |
| **WorkspaceUpdate** | `name`, `description`, `icon` |

