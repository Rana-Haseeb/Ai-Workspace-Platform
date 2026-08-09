# AI Workspace Platform — Week 5 Implementation Plan

**Goal:** A multi-user AI workspace platform where users register, create workspaces, configure
assistants, upload documents, chat with persistent history and long-term memory, reuse prompts
and skills, and monitor usage — a React single-page app on a FastAPI backend.

**Architecture:** Three hard layers. `web/` (React) talks to the platform **only** over HTTP
through `web/src/lib/api.ts`. `api/` (FastAPI) does routing, auth and validation — no business
logic. `services/` holds all business logic and is framework-free, so every service is unit
testable without starting a server. `db/` is one set of SQLAlchemy models that runs on SQLite
locally and Postgres in production. In production uvicorn serves the API **and** the built SPA,
so the whole platform is one process in one container.

**Tech Stack:**
Backend — Python 3.11, FastAPI, Uvicorn, SQLAlchemy 2.0, Pydantic v2, argon2-cffi,
python-jose, pypdf, python-docx, numpy, rank-bm25, pytest.
Frontend — React 18 + TypeScript, Vite, Tailwind CSS, shadcn/ui (Radix), TanStack Query,
React Router, lucide-react, Recharts.
LLM layer ported from Week 4 (5 providers, cross-provider failover).

**Locked decisions (approved 2026-08-09):**

| Decision | Choice |
|---|---|
| Frontend | React + Vite + Tailwind + shadcn/ui |
| Theme | Dark primary, light mode as a toggle (counts as an advanced feature) |
| Database | SQLAlchemy — SQLite local/tests, Supabase Postgres in production |
| Deployment | Hugging Face Spaces, Docker — one container, uvicorn serves API + SPA |
| Workflow | Approve each phase before it starts |

---

## Design system

From `ui-ux-pro-max`: style **Modern Dark**, pattern dense-productivity, motion tier standard.

| Token | Dark (primary) | Light (toggle) |
|---|---|---|
| `--background` | `#0F172A` | `#FAFAFC` |
| `--card` | `#192134` | `#FFFFFF` |
| `--foreground` | `#F8FAFC` | `#0F172A` |
| `--muted-foreground` | `#94A3B8` | `#64748B` |
| `--primary` | `#4338CA` | `#4338CA` |
| `--accent` | `#7C3AED` | `#7C3AED` |
| `--border` | `rgba(255,255,255,0.08)` | `#E7E5F0` |
| `--destructive` | `#DC2626` | `#DC2626` |

- **Font:** Inter (300–700), `font-variant-numeric: tabular-nums` on every dashboard figure.
- **Icons:** lucide-react only. **No emoji anywhere in the UI** — emoji-as-icon is the fastest
  way an interface reads as amateur, and it is on the skill's anti-pattern list.
- **Motion:** 150–300ms, `cubic-bezier(0.16,1,0.3,1)`, 40ms stagger on list entry, exit ~65% of
  enter duration, all wrapped in `prefers-reduced-motion`.
- **Contrast gate:** every text/background pair ≥ 4.5:1, verified in **both** themes.
- Never `#000000` as a surface (OLED smear); `#0F172A` is the floor.

**Layout — four columns:** workspace rail (56px icons) → conversation list (240px) →
chat column (fluid) → context panel (300px, collapsible, holds citations + recalled memory).
Below 1024px the rail collapses to a sheet and the context panel moves to a bottom drawer.

---

## Reuse from Week 4 (`multi-agent-research-platform`)

Copied, not rewritten. **The Week 4 theme is deliberately not reused** — the UI is new.

| Source | Destination | Change needed |
|---|---|---|
| `app/config.py` | `core/config.py` | Strip workflow budgets; add `DATABASE_URL`, JWT, embedding settings |
| `app/services/llm_service.py` | `services/llm_service.py` | Accept per-request model/temperature/max_tokens; add a streaming method |
| `app/services/usage.py` | `services/usage.py` | Write to the `logs` table instead of memory |
| `.gitignore` | `.gitignore` | Add `node_modules/`, `web/dist/`, `*.db` |
| `scripts/probe_providers.py` | `scripts/probe_providers.py` | As-is |
| `eval/metrics.py` structure | `eval/metrics.py` | New metrics, same shape |

---

## File structure

```
Ai-Workspace-Platform/
├── .env.example  .gitignore  requirements.txt  pytest.ini  Dockerfile  README.md
│
├── core/       config.py  security.py  logging.py
├── db/         base.py  models.py  seed.py
├── schemas/    auth.py workspace.py settings.py conversation.py document.py
│               memory.py prompt.py skill.py dashboard.py
├── services/   llm_service.py  usage.py  auth_service.py  workspace_service.py
│               chat_service.py  document_service.py  embedding_service.py
│               vector_store.py  retrieval_service.py  memory_service.py
│               prompt_service.py  dashboard_service.py
├── skills/     base.py  registry.py  builtin/{research,summarize,email,report,
│                                              meeting_notes,swot,task_planner,code_review}.py
├── api/        main.py  deps.py  static.py
│               routers/{auth,workspaces,settings,conversations,documents,
│                        memory,prompts,skills,dashboard}.py
│
├── web/
│   ├── package.json  vite.config.ts  tailwind.config.js  tsconfig.json
│   └── src/
│       ├── main.tsx  App.tsx  index.css        # CSS variables for both themes
│       ├── lib/api.ts                          # ONLY file that makes HTTP calls
│       ├── hooks/{useAuth,useWorkspaces,useConversation,useTheme}.ts
│       ├── components/
│       │   ├── ui/                             # shadcn primitives
│       │   ├── layout/{AppShell,WorkspaceRail,ConversationList,ContextPanel}.tsx
│       │   ├── chat/{MessageList,MessageBubble,Composer,CitationChip,SkillPalette}.tsx
│       │   ├── documents/{Uploader,DocumentTable}.tsx
│       │   ├── memory/{MemoryPanel,MemoryCard}.tsx
│       │   ├── prompts/{PromptLibrary,PromptEditor}.tsx
│       │   └── dashboard/{StatCard,UsageChart,ActivityFeed}.tsx
│       └── routes/{Login,Register,Chat,Documents,Memory,Prompts,Skills,
│                   Dashboard,Settings}.tsx
│
├── eval/       dataset.py metrics.py run_eval.py results.json      (40+ scenarios)
├── experiments/run_experiments.py results.json                     (6 experiments)
├── tests/      (20+ tests)
├── scripts/    init_db.py verify_phase0..11.py probe_providers.py
└── docs/       ARCHITECTURE.md ERD.md API.md RESEARCH_REPORT.md
                SECURITY_REVIEW.md PERFORMANCE.md BUILDER_JOURNAL.md
```

**Two rules with tests behind them (Phase 9):** no file in `services/` may import FastAPI, and
no file in `web/src/` outside `lib/api.ts` may call `fetch`.

---

## Database schema — 12 tables

Named to match the challenge's §9 list exactly, so an evaluator can tick them off one by one.

| Table | Key columns | Relationships |
|---|---|---|
| `users` | id, email (unique), password_hash, created_at | → workspaces, prompt_templates, memory_items |
| `workspaces` | id, **user_id**, name, description, icon, created_at | → settings, conversations, documents |
| `settings` | id, **workspace_id** (unique), assistant_name, role, system_prompt, model, temperature, max_tokens, personality, response_style | 1:1 with workspace |
| `conversations` | id, **workspace_id**, title, session_id, is_pinned, tags, created_at, updated_at | → messages |
| `messages` | id, **conversation_id**, role, content, citations (JSON), tokens_in, tokens_out, cost_usd, latency_ms, created_at | |
| `documents` | id, **workspace_id**, filename, mime_type, size_bytes, page_count, status, created_at | → chunks |
| `chunks` | id, **document_id**, ordinal, text, page, char_start, char_end | → embeddings |
| `embeddings` | id, **chunk_id**, model, dim, vector (JSON) | 1:1 with chunk |
| `prompt_templates` | id, **user_id**, workspace_id (nullable), title, body, category, **version**, parent_id, created_at | self-FK for versioning |
| `skills` | id, slug (unique), name, category, description, enabled | mirrors the code registry |
| `memory_items` | id, **user_id**, workspace_id, kind, content, importance, source_conversation_id, use_count, last_used_at, created_at | |
| `logs` | id, user_id, workspace_id, event, model, tokens_in, tokens_out, cost_usd, latency_ms, status, created_at | powers the dashboard |

**Two deliberate design choices to defend in the interview:**

1. **`prompt_templates.parent_id` + `version`** — editing a prompt inserts a new row pointing at
   its parent instead of mutating. That is prompt versioning, and old conversations keep
   referring to the exact prompt text that produced them.
2. **`memory_items` is not `chunks`.** Memory holds extracted facts *about the user*, retrieved
   by importance × recency and written back after conversations. Chunks hold document text,
   retrieved by similarity to the current question. Different tables, different retrieval, on
   purpose — this is the answer to *"How is memory different from RAG?"*

---

## Phases and approval gates

Each phase ends with a `scripts/verify_phaseN.py` that prints real output. A phase is not done
until that output is shown.

| Phase | Deliverable | Verification gate | BE | FE |
|---|---|---|---|---|
| 0 | Repo, config, 12 models, test harness, Vite+Tailwind+shadcn scaffold, theme tokens | All 12 tables create; `pytest` green; dark/light toggle works | 3 | 1.5 |
| 1 | Auth + user isolation + login/register screens | User A gets 403 on user B's workspace | 3 | 1.5 |
| 2 | Workspaces + assistant settings + app shell | Create workspace in UI, change temperature, reload, value persists | 2.5 | 2 |
| 3 | Persistent chat with **token streaming** | Restart server → history, titles, search intact | 3.5 | 2.5 |
| 4 | Knowledge base + document intelligence | Upload PDF → answer cites a real page → chip opens it | 5 | 2 |
| 5 | Long-term memory + context panel | Preference stated in session 1, recalled in session 2 | 3.5 | 1.5 |
| 6 | Prompt library + 6 skills + `/` palette | Test executes all 6 skills end to end | 3 | 2 |
| 7 | Dashboard + advanced features | Dashboard numbers match raw SQL counts | 2 | 3 |
| 8 | 40 eval scenarios + 6 experiments | `run_eval.py` writes real `results.json` | 5 | — |
| 9 | Tests to 20+, security review, perf report | Full `pytest` output shown | 3 | — |
| 10 | README, architecture, ERD, research report, journal | All 11 README sections present | 3 | — |
| 11 | Docker, deploy to HF Spaces, screenshots, demo prep | Live URL: register → chat → cite → recall | 3 | — |

**Total: 51 hours** (39 backend/docs + 12 frontend). The challenge budgets 40. The gap is the
FastAPI layer and the React frontend, neither of which any previous week had. Phases 8–11 are
the compressible ones if the deadline is tight.

---

# PHASE 0 — Foundations

**Backend files:** `.gitignore`, `.env.example`, `requirements.txt`, `pytest.ini`,
`core/config.py`, `core/logging.py`, `db/base.py`, `db/models.py`, `scripts/init_db.py`,
`scripts/verify_phase0.py`, `tests/conftest.py`, `tests/test_db_schema.py`
**Frontend files:** `web/` scaffold, `web/src/index.css` (theme tokens), `web/src/hooks/useTheme.ts`

### Task 0.1 — Repo skeleton and secrets hygiene

- [ ] **Step 1:** `git init`, create the directory tree, add `__init__.py` to every Python package.
- [ ] **Step 2:** Copy `.gitignore` from Week 4, then append:

```gitignore
# ---- Week 5 additions ----
*.db
data/uploads/
node_modules/
web/dist/
web/.vite/
```

- [ ] **Step 3:** Write `.env.example` with key **names only**:

```bash
# ---- LLM (ported from Week 4) ----
LLM_PROVIDER=groq
LLM_FALLBACK_PROVIDERS=groq2,google,openrouter
GROQ_API_KEY=
GOOGLE_API_KEY=
OPENROUTER_API_KEY=

# ---- Database ----
# Local dev/tests use SQLite. Production sets this to the Supabase session-pooler URL.
DATABASE_URL=sqlite:///./workspace.db

# ---- Auth ----
JWT_SECRET=
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440

# ---- Embeddings ----
EMBEDDING_PROVIDER=google
EMBEDDING_MODEL=text-embedding-004
EMBEDDING_DIM=768
CHUNK_SIZE=800
CHUNK_OVERLAP=120

# ---- API ----
CORS_ORIGINS=http://localhost:5173
MAX_UPLOAD_MB=20
RATE_LIMIT_PER_MINUTE=30
```

- [ ] **Step 4:** Verify `.env` is ignored before anything else exists:

```bash
git check-ignore -v .env
```
Expected: prints the matching `.gitignore` line. If it prints nothing, stop.

- [ ] **Step 5:** Commit — `chore: scaffold repo with secrets hygiene`

---

### Task 0.2 — `core/config.py`

- [ ] **Step 1:** Copy Week 4's `app/config.py` → `core/config.py`. Keep `PROVIDERS`,
      `provider_chain()`, `_int/_float/_bool`. Delete the workflow-budget fields
      (`max_revision_cycles`, `max_research_rounds`, etc.) — Week 5 has no agent graph.
- [ ] **Step 2:** Add the Week 5 fields to `Settings`:

```python
    # --- Database ---
    database_url: str = Field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./workspace.db"))

    # --- Auth ---
    jwt_secret: str = Field(default_factory=lambda: os.getenv("JWT_SECRET", ""))
    jwt_algorithm: str = Field(default_factory=lambda: os.getenv("JWT_ALGORITHM", "HS256"))
    jwt_expire_minutes: int = Field(default_factory=lambda: _int("JWT_EXPIRE_MINUTES", 1440))

    # --- Embeddings / chunking ---
    embedding_provider: str = Field(default_factory=lambda: os.getenv("EMBEDDING_PROVIDER", "google"))
    embedding_model: str = Field(default_factory=lambda: os.getenv("EMBEDDING_MODEL", "text-embedding-004"))
    embedding_dim: int = Field(default_factory=lambda: _int("EMBEDDING_DIM", 768))
    chunk_size: int = Field(default_factory=lambda: _int("CHUNK_SIZE", 800))
    chunk_overlap: int = Field(default_factory=lambda: _int("CHUNK_OVERLAP", 120))

    # --- API ---
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
            if o.strip()
        ])
    max_upload_mb: int = Field(default_factory=lambda: _int("MAX_UPLOAD_MB", 20))
    rate_limit_per_minute: int = Field(default_factory=lambda: _int("RATE_LIMIT_PER_MINUTE", 30))

    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")
```

- [ ] **Step 3:** Write the test `tests/test_config.py`:

```python
from core.config import settings

def test_sqlite_is_the_local_default():
    assert settings.is_sqlite()
    assert settings.database_url.startswith("sqlite")

def test_no_secret_has_a_hardcoded_default():
    # A real secret must come from the environment, never from source.
    assert settings.jwt_secret == "" or len(settings.jwt_secret) >= 16
```

- [ ] **Step 4:** Run `pytest tests/test_config.py -v` → PASS.
- [ ] **Step 5:** Commit — `feat: port Week 4 config, add DB/auth/embedding settings`

---

### Task 0.3 — `db/base.py` (the dual-dialect switch)

- [ ] **Step 1:** Write `db/base.py`:

```python
"""Engine and session factory.

One set of models serves two dialects. SQLite gets ``check_same_thread=False`` because
FastAPI serves requests on a threadpool; Postgres gets connection pooling with
``pool_pre_ping`` so Supabase's pooler dropping an idle connection does not surface as a
500. Nothing else in the codebase knows which database is underneath — that is the point.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from core.config import settings


def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_pre_ping": True, "pool_size": 5, "max_overflow": 10}


engine = create_engine(settings.database_url, **_engine_kwargs(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass
```

- [ ] **Step 2:** Commit — `feat: SQLAlchemy engine with SQLite/Postgres switch`

---

### Task 0.4 — `db/models.py` (all 12 tables)

- [ ] **Step 1:** Write all 12 models in one file, in the dependency order of the schema table
      above. Every foreign key that scopes data to a user gets `index=True` and
      `ondelete="CASCADE"`. Sample of the first three; the rest follow the same shape:

```python
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    workspaces: Mapped[list["Workspace"]] = relationship(
        back_populates="user", cascade="all, delete-orphan")


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    icon: Mapped[str] = mapped_column(String(40), default="flask")   # lucide icon name
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="workspaces")
    settings: Mapped["Settings"] = relationship(
        back_populates="workspace", uselist=False, cascade="all, delete-orphan")


class Settings(Base):
    """The assistant configuration for one workspace (challenge §9 'Settings')."""
    __tablename__ = "settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), unique=True, index=True)
    assistant_name: Mapped[str] = mapped_column(String(120), default="Assistant")
    role: Mapped[str] = mapped_column(String(200), default="General assistant")
    system_prompt: Mapped[str] = mapped_column(Text, default="You are a helpful assistant.")
    model: Mapped[str | None] = mapped_column(String(120), default=None)
    temperature: Mapped[float] = mapped_column(Float, default=0.3)
    max_tokens: Mapped[int] = mapped_column(Integer, default=2048)
    personality: Mapped[str] = mapped_column(String(60), default="professional")
    response_style: Mapped[str] = mapped_column(String(60), default="balanced")

    workspace: Mapped["Workspace"] = relationship(back_populates="settings")
```

Note `icon` stores a **lucide icon name**, not an emoji — the no-emoji rule reaches the schema.

- [ ] **Step 2:** Commit — `feat: 12-table schema for users through logs`

---

### Task 0.5 — Test harness and the schema test

- [ ] **Step 1:** Write `tests/conftest.py` — an in-memory database per test, so tests need no
      network and no cleanup:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.base import Base


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,   # one shared in-memory DB across the test's connections
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
```

- [ ] **Step 2:** Write the failing test `tests/test_db_schema.py`:

```python
from sqlalchemy import inspect

EXPECTED = {
    "users", "workspaces", "settings", "conversations", "messages",
    "documents", "chunks", "embeddings", "prompt_templates", "skills",
    "memory_items", "logs",
}

def test_all_twelve_tables_exist(db):
    actual = set(inspect(db.get_bind()).get_table_names())
    assert EXPECTED <= actual, f"missing: {EXPECTED - actual}"

def test_deleting_a_user_cascades_to_their_workspaces(db):
    from db.models import User, Workspace
    u = User(email="a@b.c", password_hash="x")
    u.workspaces.append(Workspace(name="Research"))
    db.add(u); db.commit()
    db.delete(u); db.commit()
    assert db.query(Workspace).count() == 0
```

- [ ] **Step 3:** Run `pytest tests/ -v` → FAIL first, then PASS once models land.
- [ ] **Step 4:** Write `scripts/verify_phase0.py` — creates the real SQLite file, prints each
      table with its column count, exits non-zero if any of the 12 is missing.
- [ ] **Step 5:** Run `python scripts/verify_phase0.py` and **show the output**.
- [ ] **Step 6:** Commit — `test: in-memory DB fixture and 12-table schema test`

---

### Task 0.6 — Frontend scaffold and theme tokens

- [ ] **Step 1:** Scaffold and install:

```bash
npm create vite@latest web -- --template react-ts
```

- [ ] **Step 2:** Add Tailwind and shadcn/ui, then the base primitives:

```bash
npx shadcn@latest add button input card dialog dropdown-menu sidebar table tabs badge sonner
```

- [ ] **Step 3:** Write `web/src/index.css` with both themes as CSS variables, dark as the
      default on `:root` and light under `.light`:

```css
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

:root {
  --background: 222 47% 11%;      /* #0F172A */
  --card: 222 38% 15%;            /* #192134 */
  --foreground: 210 40% 98%;      /* #F8FAFC */
  --muted-foreground: 215 20% 65%;
  --primary: 243 75% 51%;         /* #4338CA */
  --accent: 262 83% 58%;          /* #7C3AED */
  --border: 0 0% 100% / 0.08;
  --destructive: 0 72% 51%;
  --radius: 0.625rem;
}
.light {
  --background: 260 40% 99%;
  --card: 0 0% 100%;
  --foreground: 222 47% 11%;
  --muted-foreground: 215 16% 47%;
  --border: 258 30% 92%;
}
* { font-family: Inter, system-ui, sans-serif; }
.tabular { font-variant-numeric: tabular-nums; }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
}
```

- [ ] **Step 4:** Write `web/src/hooks/useTheme.ts` — toggles the `light` class on
      `document.documentElement` and persists the choice in `localStorage`.
- [ ] **Step 5:** Verify: `npm run dev`, toggle the theme, confirm both modes render and no
      element disappears in either. **Show a screenshot of both.**
- [ ] **Step 6:** Commit — `feat: Vite + Tailwind + shadcn scaffold with dark/light tokens`

### ✅ Phase 0 gate

```bash
python scripts/init_db.py && python scripts/verify_phase0.py && pytest -v
```
Plus `npm run dev` in `web/` with the theme toggle working in both directions.
Passes when: all 12 tables exist with the documented columns, cascade delete works,
`git check-ignore .env` confirms the env file can never be committed, and both themes render
with no invisible text.

---

# PHASES 1–11 — specifications

Step-level tasks get written at the start of each phase, once the previous gate has passed.
Writing all 12 phases at step granularity now would lock in decisions before the code that
informs them exists. Each phase below states what it must produce and how it is proven.

### Phase 1 — Authentication
argon2 password hashing (not bcrypt — its 72-byte truncation is a real defect), JWT bearer
tokens, `get_current_user` dependency. Every workspace-scoped query filters on `user_id` taken
from the **token**, never from a request body. Login and register screens.
**Gate:** a test where user A requests user B's workspace and receives 403 — the concrete
answer to *"How would you isolate user data?"*

### Phase 2 — Workspaces, assistant settings, app shell
Workspace CRUD; a `settings` row auto-created per workspace with the 8 configurable fields.
The four-column `AppShell` with workspace rail and conversation list.
**Gate:** create a workspace in the UI, change temperature and system prompt, reload the
browser, values persist.

### Phase 3 — Persistent chat with streaming
Sessions, titles auto-generated from the first message, rename, delete, search, token/cost/
latency recorded per message. FastAPI `StreamingResponse` + a `ReadableStream` reader on the
client so tokens appear as they generate.
**Gate:** restart the API process, reload — history, titles and search all intact.

### Phase 4 — Knowledge base and document intelligence
PDF/DOCX/TXT/MD parsing, overlapping chunking with page offsets, Google embeddings,
`VectorStore` abstraction (`JsonCosineStore` everywhere, `PgVectorStore` when Postgres is
available), hybrid BM25 + vector retrieval, citations carrying document and page. Drag-and-drop
uploader with real progress.
**Gate:** upload a real PDF, ask a question, receive an answer whose citation chip opens the
correct page.

### Phase 5 — Long-term memory and the context panel
After each exchange, an extraction call pulls durable facts (preferences, recurring topics) and
writes `memory_items`. Retrieval ranks by importance × recency and injects a bounded budget into
the system prompt. Manual pin/unpin/delete. The context panel shows which memories were used in
the current answer.
**Gate:** state a preference in session 1; a brand-new session in a fresh process applies it.

### Phase 6 — Prompt library and 6+ skills
Prompt CRUD with immutable versioning (`parent_id`). Skill registry where a skill is one file
plus one registry line — deliberately shaped for the live code review. A `/` command palette in
the composer.
**Gate:** a parameterised test runs every registered skill and asserts a non-empty typed result;
adding a 7th skill is demonstrated live as a 2-file change.

### Phase 7 — Dashboard and advanced features
Dashboard reads from `logs`: conversations, documents, memory items, prompts, tokens, estimated
cost, recent activity, with Recharts visualisations.
Advanced features (5, one more than required): **dark/light toggle**, **conversation export
(Markdown + PDF)**, **conversation search**, **pinned messages + tags**, and **multi-model
switching** — nearly free because `llm_service` already drives 5 providers.
**Gate:** every dashboard number equals the raw SQL count it claims to represent.

### Phase 8 — Evaluation and experiments
40+ scenarios across the 7 required categories, scored on accuracy, response time, memory
recall, citation quality, task success. Six experiments: memory on/off, short vs detailed
prompt, model comparison, small vs large context, conversation length, chunk size.
**Gate:** `python eval/run_eval.py` and `python experiments/run_experiments.py` write real
results files from real model calls — no synthetic numbers.

### Phase 9 — Tests, security review, performance
Tests to 20+ across the 10 required areas, plus two architecture tests: nothing in `services/`
imports FastAPI, and nothing in `web/src/` outside `lib/api.ts` calls `fetch`. Security review
covering all 10 topics, including a live prompt-injection test against an uploaded document
containing an embedded instruction. Performance report with the 8 required measurements.
**Gate:** full `pytest` output shown; measurements are recorded numbers, not estimates.

### Phase 10 — Documentation
README (11 sections), architecture doc, ERD, API docs generated from the live OpenAPI schema,
research report (≤5 pages), builder journal (≤2 pages).
**Gate:** every §20 README section present and non-empty.

### Phase 11 — Deployment
Multi-stage Dockerfile: node builds `web/dist`, python serves it. `api/static.py` mounts the SPA
with a catch-all so client-side routes survive a refresh. Deployed to Hugging Face Spaces with
secrets set in the Space and `DATABASE_URL` pointed at Supabase Postgres.
**Gate:** on the live URL — register a new account, create a workspace, upload a document, get a
cited answer, and have memory recall in a second session.

---

## Still needed from the user

1. **Deadline / onsite date** — determines whether phases 8–11 get compressed.
2. **Dependency approval** — backend: `fastapi`, `uvicorn`, `sqlalchemy`, `argon2-cffi`,
   `python-jose`, `pypdf`, `python-docx`, `numpy`. Frontend: `react`, `vite`, `tailwindcss`,
   `shadcn/ui` (+ radix, cva, clsx, tailwind-merge), `@tanstack/react-query`,
   `react-router-dom`, `lucide-react`, `recharts`.
3. **Node.js availability** — needs Node 18+ locally to build the frontend.
4. **GitHub repo name and account** — needed at Phase 11.
5. **Confirm Week 4 reuse** by copying the five files in the reuse table.
