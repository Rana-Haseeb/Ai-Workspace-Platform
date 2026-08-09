<div align="center">

# AI Workspace Platform

**A multi-user AI workspace where every answer can be traced — to a document page, or to
something you said three sessions ago.**

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-CA4245?style=for-the-badge)](https://sqlalchemy.org)
[![Tests](https://img.shields.io/badge/tests-124_passing-success?style=for-the-badge)](tests/)
[![WCAG](https://img.shields.io/badge/WCAG-AA_verified-0F9D58?style=for-the-badge)](scripts/check_contrast.js)

<samp>Visibility Bots Innovation Lab · AI Summer Fellowship 2026 · Track 2: NLP & AI Agents · **Week 5**</samp>

</div>

---

> ### The question this repo exists to answer
>
> **"What separates an AI demo from an AI platform?"**
>
> A demo answers one person's question once. A platform serves many people, keeps what it
> learns, proves where its answers came from, and can be handed to someone else to operate.
> This is an attempt at the second thing.

---

## Contents

- [Problem statement](#problem-statement)
- [Build status](#build-status)
- [Features](#features)
- [Technology stack](#technology-stack)
- [Architecture](#architecture)
- [Database](#database)
- [Installation](#installation)
- [API endpoints](#api-endpoints)
- [Testing and verification](#testing-and-verification)
- [Design system](#design-system)
- [Measured performance](#measured-performance)
- [Deployment](#deployment)
- [Screenshots](#screenshots)
- [Evaluation results](#evaluation-results)
- [Known limitations](#known-limitations)
- [Future improvements](#future-improvements)

---

## Problem statement

Most AI assistants forget you between sessions, cannot tell you where an answer came from, and
assume a single user. That is fine for a demo and useless for a team.

An organisation that wants to actually use an AI assistant needs answers to questions a demo
never has to face:

- **Whose data is this?** Several people share a deployment. One user's documents, conversations
  and memory must be unreachable by another — not by convention, but by construction.
- **Where did this answer come from?** A confident paragraph with no source is a liability. Every
  factual claim should carry a citation a human can open and check.
- **What does it know about me?** Repeating your context at the start of every session is the
  clearest sign a tool is not really yours.
- **What is this costing?** Tokens and money are consumed per message. Somebody has to be able
  to see that number.

This platform is built around those four questions.

---

## Build status

Built in verified phases. Each ends with a script that prints real output; nothing is called
done until that output passes.

| Phase | What it delivers | Status |
|---|---|:--:|
| 0 | Repo, config, 12-table schema, test harness, React scaffold, dual theme | ✅ |
| 1 | Authentication, argon2 hashing, JWT sessions, tenant isolation | ✅ |
| 2 | Workspace CRUD, the 8 assistant settings, the app shell | ✅ |
| 3 | Persistent chat with token streaming | ✅ |
| 4 | Knowledge base and document intelligence with citations | ⬜ |
| 5 | Long-term memory | ⬜ |
| 6 | Prompt library and reusable skills | ⬜ |
| 7 | Dashboard and advanced features | ⬜ |
| 8 | 40 evaluation scenarios, 6 experiments | ⬜ |
| 9 | Full test suite, security review, performance report | ⬜ |
| 10 | Architecture docs, ERD, research report, builder journal | ⬜ |
| 11 | Deployment | ⬜ |

The full plan, including the specification and gate for every phase, is in
[docs/PLAN.md](docs/PLAN.md).

**Currently passing:**

```
124 tests passed
PHASE 0 PASSED - 12 tables, 8 settings fields, 7 indexed keys, 2 themes.
PHASE 1 PASSED - argon2 hashing, signed sessions, and 403 isolation verified.
PHASE 2 PASSED - workspace CRUD, 8 assistant fields, validation, persistence.
PHASE 3 PASSED - live replies, titling, history, streaming, search, persistence.
All pairs meet WCAG AA.
```

Phase 3's gate is the only one that calls a real provider, because what it verifies is that a
real reply arrives, is stored, and is still there afterwards. The test suite stays offline.

---

## Features

### Working now

| Feature | Detail |
|---|---|
| **Registration and login** | argon2id hashing, no 72-byte truncation. Login failures are indistinguishable whether or not the account exists |
| **Sessions** | Signed JWT in an httpOnly cookie, so an XSS bug cannot read it. Bearer header supported for API clients |
| **Tenant isolation** | Every workspace-scoped route passes through one ownership dependency. Another user gets 403, an anonymous caller gets 401 |
| **Multiple workspaces** | Each with its own name, description, icon, and independent assistant configuration |
| **Assistant configuration** | All eight fields — name, role, system prompt, model, temperature, max tokens, personality, response style — plus memory and knowledge-base toggles |
| **Persistent chat** | Conversations per workspace, full transcript, timestamps, session ids. Survives a server restart |
| **Token streaming** | Replies appear word by word over NDJSON, with a stop button that actually aborts the request |
| **Automatic titles** | Named from the opening message, with a fallback to the message itself if the naming call fails |
| **Search** | Matches conversation titles *and* message bodies, so a half-remembered phrase finds the thread |
| **Rename, pin, tag, delete** | Pinned conversations sort first; tags are de-duplicated and capped |
| **Per-message usage** | Model, token counts and latency recorded on every reply and mirrored into `logs` |
| **Dark and light themes** | Dark by default, applied before first paint. Every colour pair verified against WCAG AA in both |

### Coming in later phases

Document upload with cited answers · long-term memory · prompt library with versioning ·
six reusable skills · usage dashboard · conversation export.

---

## Technology stack

**Backend** — Python 3.13, FastAPI, Uvicorn, SQLAlchemy 2.0, Pydantic v2, argon2-cffi,
python-jose, pypdf, python-docx, numpy, rank-bm25, pytest.

**Frontend** — React 19, TypeScript, Vite, Tailwind CSS v4, shadcn/ui on Base UI,
TanStack Query, React Router, lucide-react, Recharts.

**Data** — SQLite locally and in tests, PostgreSQL (Supabase) in production. One set of models
serves both.

**Models** — seven OpenAI-compatible providers (Groq ×3 organisations, Google AI Studio,
OpenRouter, xAI, OpenAI) behind one client, with automatic cross-provider failover.

### Two choices worth explaining

**SQLAlchemy over raw SQL.** The same models run on SQLite and PostgreSQL, so the test suite
needs no network and finishes in seconds while production runs real Postgres. Moving between
them is one environment variable.

**Cross-provider failover, carried over from Week 4.** A live deployment there hit its rate
limit mid-run: 216 calls attempted, 164 refused, no second backend to fall to. Multi-user
traffic makes that more likely, not less, so the provider chain came across unchanged.

---

## Architecture

```
                            React SPA  (web/)
                                 │
                    all HTTP goes through lib/api.ts
                                 │
    ────────────────────────────────────────────────────────
                          FastAPI  (api/)
              routing · validation · auth · ownership
                                 │
    ────────────────────────────────────────────────────────
                    Business logic  (services/)
       auth · workspaces · chat · documents · memory · skills
                    no framework imports allowed
                                 │
    ────────────────────────────────────────────────────────
                       SQLAlchemy  (db/)
                                 │
                    SQLite  ·or·  PostgreSQL
```

Three rules hold this shape, and two of them have tests behind them (Phase 9):

1. **Nothing in `services/` may import FastAPI.** Every service is testable by calling a
   function — no server, no client, no HTTP.
2. **Nothing in `web/src/` outside `lib/api.ts` may call `fetch`.** The API surface is
   discoverable in one file.
3. **Ownership is checked in exactly one place.** `get_owned_workspace` in
   [api/deps.py](api/deps.py) is the only code that decides whether you may touch a workspace.
   Isolation implemented once is auditable; implemented per route, it is a rule someone
   eventually forgets.

### Project layout

```
core/       config, security (hashing + tokens), logging
db/         engine, session factory, the 12 models
schemas/    Pydantic request/response models — the API contract
services/   business logic, framework-free
skills/     skill registry and built-in skills          (Phase 6)
api/        FastAPI app, dependencies, routers
web/        React SPA
eval/       evaluation dataset and results              (Phase 8)
experiments/ experiment scripts and results             (Phase 8)
tests/      pytest suite
scripts/    init_db, per-phase verification, contrast audit
docs/       plan, architecture, ERD, reports
```

---

## Database

Twelve tables, named to match the challenge's specification one for one.

| Table | Holds | Scoped by |
|---|---|---|
| `users` | Accounts and password hashes | — |
| `workspaces` | Name, description, icon | `user_id` |
| `settings` | Assistant configuration, 1:1 with a workspace | `workspace_id` |
| `conversations` | Title, session id, tags, pinned state | `workspace_id` |
| `messages` | Role, content, citations, tokens, cost, latency | `conversation_id` |
| `documents` | Filename, type, size, pages, ingestion status | `workspace_id` |
| `chunks` | Text fragment with its page and character offsets | `document_id` |
| `embeddings` | One vector per chunk | `chunk_id` |
| `prompt_templates` | Saved prompts, versioned by insertion | `user_id` |
| `skills` | Registry mirror, enable flags, usage counts | — |
| `memory_items` | Durable facts about the user | `user_id` |
| `logs` | Every billable event; the dashboard reads this | `user_id` |

### Three decisions to defend

**`memory_items` is not `chunks`.** Both store text and both get retrieved, so merging them is
tempting and wrong. A chunk is a fragment of a *document*, retrieved by similarity to the
current question, immutable once ingested. A memory item is a fact about the *user* — a
preference, a recurring topic — extracted after a conversation, retrieved by importance and
recency, and updated as their situation changes. Different lifecycle, different retrieval,
different table. A test proves the point: deleting the document a memory was learned from leaves
the memory intact.

**Prompts are versioned by insertion, not mutation.** Editing writes a new row whose `parent_id`
points at the previous one and whose `version` increments. Nothing overwrites history, so a
conversation from last week can still be traced to the exact prompt text that produced it.

**Embedding vectors are stored as JSON, not a native vector type.** The same schema then runs on
SQLite and PostgreSQL unchanged. Similarity is computed behind a `VectorStore` interface, so
adopting pgvector later is a new implementation of that interface — not a migration for
everything that reads it.

---

## Installation

**Requirements:** Python 3.11+, Node 18+.

```bash
git clone <your-repo-url>
cd Ai-Workspace-Platform
```

**1. Backend dependencies**

```bash
python -m pip install -r requirements.txt
```

**2. Environment**

```bash
cp .env.example .env
```

Then generate a signing key and put it in `.env` as `JWT_SECRET`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Everything else has a working default. `.env` is gitignored — confirm with
`git check-ignore -v .env` before your first commit.

**3. Database**

```bash
python scripts/init_db.py
```

Creates `workspace.db` locally. For production, set `DATABASE_URL` to a PostgreSQL connection
string and re-run; nothing else changes.

**4. Frontend dependencies**

```bash
npm install --prefix web
```

**5. Run it — two terminals**

```bash
python -m uvicorn api.main:app --reload
```

```bash
npm run dev --prefix web
```

The app is at `http://localhost:5173`. Interactive API docs are at
`http://127.0.0.1:8000/docs`.

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./workspace.db` | The one switch between SQLite and PostgreSQL |
| `JWT_SECRET` | *(none)* | Signing key. Empty means a random per-process key and a loud warning |
| `JWT_EXPIRE_MINUTES` | `1440` | Session lifetime |
| `LLM_PROVIDER` | `groq` | Primary model provider |
| `LLM_FALLBACK_PROVIDERS` | `groq2,groq3,google,openrouter` | Tried in order when the primary fails |
| `GROQ_API_KEY` etc. | *(none)* | Provider keys. Unconfigured providers are skipped automatically |
| `EMBEDDING_PROVIDER` | `google` | Embedding backend for the knowledge base |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `800` / `120` | Document chunking, in characters |
| `CORS_ORIGINS` | `http://localhost:5173` | Development only; production is same-origin |
| `MAX_UPLOAD_MB` | `20` | Upload ceiling |

No secret has a hard-coded default anywhere in the source. A test enforces it.

---

## API endpoints

Full interactive documentation is generated from the code at `/docs`.

### Authentication

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/auth/register` | Create an account, receive a session |
| `POST` | `/api/auth/login` | Sign in |
| `POST` | `/api/auth/logout` | Clear the session cookie |
| `GET` | `/api/auth/me` | The authenticated user |

### Workspaces

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/workspaces/meta` | Icons, models and option lists the UI renders from |
| `POST` | `/api/workspaces` | Create a workspace and its assistant configuration |
| `GET` | `/api/workspaces` | List your own — never anyone else's |
| `GET` | `/api/workspaces/{id}` | One workspace with its settings |
| `PATCH` | `/api/workspaces/{id}` | Rename, re-describe, change icon |
| `DELETE` | `/api/workspaces/{id}` | Delete it and everything inside |
| `GET` | `/api/workspaces/{id}/settings` | Assistant configuration |
| `PATCH` | `/api/workspaces/{id}/settings` | Update any subset of the eight fields |

### Conversations

All nested under `/api/workspaces/{workspace_id}`, so every one inherits the ownership check.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/conversations?q=` | List, newest first, pinned on top. `q` searches titles and message bodies |
| `POST` | `/conversations` | Start an empty conversation |
| `GET` | `/conversations/{id}` | Full transcript |
| `PATCH` | `/conversations/{id}` | Rename, pin, tag |
| `DELETE` | `/conversations/{id}` | Delete it and its messages |
| `POST` | `/conversations/{id}/messages` | Send a message, get the finished reply as JSON |
| `POST` | `/conversations/{id}/stream` | Send a message, get NDJSON events as it generates |
| `PATCH` | `/conversations/{id}/messages/{mid}/pin` | Pin or unpin a message |

**Why NDJSON and not Server-Sent Events.** SSE adds `data:` prefixes and blank-line terminators
to parse around, and its automatic reconnection is actively unwanted here — a dropped chat
stream should surface, not silently replay. One JSON object per line is simpler on both sides.

Stream events: `start` → `token`* → `done`, or `error` in place of `done`.

### Meta

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Liveness. Reports no secrets and no connection strings |

**Status codes used deliberately:** `401` means not authenticated; `403` means authenticated but
not yours; `404` means no such workspace; `409` means the email is taken; `422` means the request
failed validation.

---

## Testing and verification

```bash
python -m pytest -v
```

Every test runs against an in-memory SQLite database created per test, so the suite needs no
network, no fixtures on disk and no cleanup. `StaticPool` keeps one connection alive for the
engine's lifetime — without it, every checkout would open a *new* empty in-memory database and
the tables would vanish before the code under test saw them.

`PRAGMA foreign_keys=ON` is set per connection. SQLite ships with foreign-key enforcement off,
so without it a cascade-delete test would pass for the wrong reason.

### Per-phase gates

```bash
python scripts/verify_phase0.py     # schema, indexes, secrets hygiene, theme tokens
python scripts/verify_phase1.py     # hashing, tokens, 403 isolation
python scripts/verify_phase2.py     # workspace CRUD, the 8 fields, validation, persistence
node   scripts/check_contrast.js    # WCAG AA across both themes
```

Each prints what it checked and exits non-zero on failure, so the result is evidence rather than
a claim.

### What the tests actually guard

- A user requesting another user's workspace receives 403 — the isolation guarantee
- A `user_id` in a request body is ignored; ownership comes from the token
- Two 72-byte-plus passwords stay distinguishable (the bcrypt defect)
- An unknown email takes comparable time to a wrong password — no account enumeration by timing
- A deleted user's still-valid token is rejected on the next request
- Deleting a user cascades through workspaces, conversations, messages, documents, chunks and
  embeddings
- Deleting a document leaves memory learned from it intact
- Editing a prompt creates a version instead of overwriting

---

## Design system

Chosen with the `ui-ux-pro-max` design database, then measured rather than eyeballed.

| | Dark (default) | Light |
|---|---|---|
| Page | `#0F172A` | `#FAFAFC` |
| Card | `#192134` | `#FFFFFF` |
| Primary | `#5B54EA` | `#4338CA` |
| Brand accent | `#A78BFA` | `#7C3AED` |
| Text | `#F8FAFC` | `#0F172A` |
| Secondary text | `#94A3B8` | `#64748B` |

**Type:** Inter, self-hosted — no external font request at runtime. Tabular figures on every
number that changes, so counters do not jitter as they update.

**Icons:** lucide-react only. **No emoji anywhere**, including in the database: `workspaces.icon`
stores a lucide name, and the API replaces an emoji with a valid name rather than storing it.
Emoji render differently on every platform and cannot take the theme's colour.

**Contrast is measured, not assumed.** [scripts/check_contrast.js](scripts/check_contrast.js)
reads the oklch values out of the stylesheet, converts them to sRGB and checks all 20 pairs in
both themes against WCAG AA — 4.5:1 for text, 3.0:1 for component boundaries. It needs no
browser, so it runs in CI.

It has already caught one real failure. White on the original dark-mode indigo `#6366F1` gives
**4.47:1** — below the 4.5 minimum, and invisible to the eye. Five candidates were tested against
both requirements at once:

| Candidate | Label on button (≥4.5) | Button vs page (≥3.0) | |
|---|---|---|---|
| `#4338CA` | 7.90 ✅ | 2.26 ❌ | too dark to separate |
| `#4F46E5` | 6.29 ✅ | 2.84 ❌ | still too dark |
| **`#5B54EA`** | **5.38 ✅** | **3.32 ✅** | **chosen** |
| `#6366F1` | 4.47 ❌ | 4.00 ✅ | the original |

**Motion** is 150–300ms with `prefers-reduced-motion` respected globally: users who asked their
OS to reduce motion get a static interface, not a slower one.

---

## Measured performance

Numbers from this machine against Groq, not estimates. Reproduce with
`python scripts/verify_phase3.py`.

| Model | Full reply | Time to first token | Stream total |
|---|---|---|---|
| `llama-3.3-70b-versatile` | 0.24s | 0.17s | 0.19s |
| `openai/gpt-oss-120b` | 0.40s | 0.43s | 0.61s |
| `openai/gpt-oss-20b` | 0.43s | 0.17s | 0.18s |

### The cold start that was hiding in these numbers

An early measurement showed `gpt-oss-120b` taking **20.3 seconds** for a one-sentence answer
while the other two took under half a second. The obvious conclusion — that model is slow — was
wrong.

`llm_service` imports `langchain_openai` lazily, inside the client factory. That import takes
**18 seconds** the first time in a process. Whichever model happened to be called first paid it,
and in that run it was `gpt-oss-120b`. Re-measuring with the import warmed put all three models
under a second.

The measurement bug was real, though: it meant the *first user message after every server start*
was recorded at 20.7s instead of 0.2s. The fix is in `api/main.py` — the import now happens
during startup, so the cost lands where nobody is waiting:

```
Model client warmed in 18.4s
API ready - SQLite, provider chain: groq
```

First message after a fresh start is now 2.5s (the remaining time is the first TLS handshake to
the provider), and subsequent messages are ~0.2s.

**The lesson, recorded because it will happen again:** a latency number from the first call in a
process is measuring your imports, not your model.

---

## Deployment

*Arrives in Phase 11.* The plan: a multi-stage Dockerfile where Node builds `web/dist` and
Python serves it, deployed to Hugging Face Spaces. Uvicorn serves the API and the built SPA from
one origin, so the whole platform is one process in one container and the session cookie needs
no cross-origin handling. `DATABASE_URL` points at Supabase PostgreSQL; the models do not change.

---

## Screenshots

*Added in Phase 11, once every screen exists.*

---

## Evaluation results

*Arrives in Phase 8:* 40+ scenarios across knowledge questions, document questions, memory
questions, conversation continuation, prompt templates, skill invocation and edge cases —
scored on accuracy, response time, memory recall, citation quality and task success. Plus six
experiments, including memory on versus off, and chunk-size comparison.

---

## Known limitations

Stated plainly, because a limitation you have written down is a decision, and one you have not
is a surprise.

- **Logout cannot revoke a token that has already left the browser.** A signed JWT is valid until
  it expires; clearing the cookie is what logout means here. The 24-hour expiry bounds the rest.
  A revocation denylist is the fix and is not built.
- **403 rather than 404 on another user's workspace** leaks that the id exists. Ids are
  sequential integers, so existence is already guessable; the clearer error was judged worth
  more than the marginal concealment.
- **`create_all` is not a migration tool.** Adding a column to an existing database needs a
  manual migration. Locally, delete `workspace.db` and re-run `init_db.py`.
- **No rate limiting yet.** `RATE_LIMIT_PER_MINUTE` is configured and not yet enforced. Chat is
  now the expensive route, so this is the next thing to close.
- **Streaming token counts are estimated.** A streamed response carries no usage block, so
  input and output tokens are approximated as characters/4. Non-streamed replies use the
  provider's reported counts. The dashboard labels which is which.
- **Streaming failover only works before the first token.** Once text has reached the browser
  the platform cannot silently switch providers, so a mid-reply failure surfaces as an error
  rather than restarting on another backend.
- **History is trimmed by turn count, not tokens.** The last 20 messages are replayed. A very
  long single message could still crowd the window; Phase 8's conversation-length experiment
  measures what this costs.
- **Phases 4–11 are not built.** The sidebar shows those sections disabled with the phase they
  arrive in, rather than hiding them.

---

## Future improvements

- Token revocation list, so logout invalidates server-side
- pgvector behind the existing `VectorStore` interface once the corpus outgrows in-memory cosine
- Workspace sharing between users, which needs a membership table and a permission model
- Background ingestion queue so large document uploads do not hold a request open
- Streaming evaluation, so the evaluation harness measures time-to-first-token as well as total

---

<div align="center">
<samp>Built for the Visibility Bots AI Summer Fellowship 2026 · Week 5</samp>
</div>
