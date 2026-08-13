# Running the platform

Everything you need to start it, look at it, and check it is working.

---

## Start it — two terminals

The platform is two processes in development: a Python API and a React dev server. You need
both, in **separate terminals**, both left running.

### Terminal 1 — the API

```bash
cd "D:/Coding Files/InternShip/Visibility Bots Internship/Ai-Workspace-Platform" && python -m uvicorn api.main:app --reload
```

Wait for:

```
Model client warmed in 18.4s
API ready - SQLite, provider chain: groq -> google
Uvicorn running on http://127.0.0.1:8000
```

The 18 seconds is a one-off import cost paid at startup so the first chat message is fast.
`--reload` restarts it when you change Python files — always use it while developing.

### Terminal 2 — the web app

```bash
cd "D:/Coding Files/InternShip/Visibility Bots Internship/Ai-Workspace-Platform" && npm run dev --prefix web
```

Then open **http://localhost:5173**.

### Stop them

`Ctrl+C` in each terminal. If a port is stuck:

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

---

## First run

1. Open http://localhost:5173 — you land on the sign-in screen.
2. Click **Create an account**. Any email works (`you@example.com`), password 8+ characters.
   Nothing is emailed anywhere; accounts are local.
3. Create a workspace. Name it anything, pick an icon.
4. You are in.

---

## What to try, in the order that shows the most

**Chat** — click *New chat*, ask anything. Words appear as they generate.

**Documents** — go to *Documents*, drag in a PDF. Watch it go `Processing → Ready` with a page
and chunk count. Then go back to chat and ask a question about it. The answer carries numbered
**source chips**; click one and it opens the exact page text the model was given.

**Memory** — in a chat, say something like:

> *I'm a backend engineer and I always want answers in British English, under three sentences.*

Then open **Memory**. The model extracted that on its own. Now start a **new chat** and ask
something unrelated — the answer follows the preference, and a chip under it says
*"Remembered 3 things about you"*.

**Skills** — type `/` in the chat box. Arrow keys, Enter to pick. Try `/swot` with
*"Launching a paid tier for our developer tool"* — it comes back as four proper lists.

**Prompts** — save a prompt, then edit it. It becomes **version 2** and the old text stays in
the history icon. Nothing is overwritten.

**Dashboard** — counts, token usage, a 14-day chart, and where the tokens went.

**Export** — the download icon at the top of a chat. Markdown file, or print to PDF.

**Dark mode** — the sun/moon icon, top right.

---

## Checking it works

All of these run from the project root.

```bash
python -m pytest
```

406 tests, about 70 seconds, and **genuinely no network** — verified by running the whole suite
with a deliberately invalid `GOOGLE_API_KEY`, which still passes. That claim used to be false:
the chat path embeds every query for retrieval, so any test sending a message was quietly calling
the live Google API. It passed on available quota and hung for minutes per test once the free
tier started returning 429.

### The phase gates

Each prints what it checked rather than just passing:

```bash
python scripts/verify_phase0.py
```
```bash
python scripts/verify_phase1.py
```
```bash
python scripts/verify_phase2.py
```
```bash
python scripts/verify_phase7.py
```
```bash
python scripts/verify_phase8.py
```
```bash
python scripts/verify_phase10.py
```

```bash
python scripts/benchmark.py --offline
```

These five call the **real model providers**, so they need your API keys and take a minute:

```bash
python scripts/verify_phase3.py
```
```bash
python scripts/verify_phase4.py
```
```bash
python scripts/verify_phase5.py
```
```bash
python scripts/verify_phase6.py
```
```bash
python scripts/verify_phase9.py
```

And this one needs a **running deployment** — the container, or the live Space:

```bash
python scripts/verify_phase11.py
```
```bash
python scripts/verify_phase11.py --url https://<user>-<space>.hf.space
```

### Other checks

```bash
node scripts/check_contrast.js
```
Colour contrast in both themes, against WCAG AA.

```bash
node scripts/check_frontend_rules.js
```
Structural rules a type checker cannot see: only `lib/api.ts` talks HTTP, the shell has a
working scroll container, scrollbars are styled, no emoji used as icons.

```bash
python scripts/seed_demo.py --reset
```
Fills a workspace with real content — documents, conversations, memory, prompts — so every screen
has something on it. Needs the API running. Sign in with `demo@example.com` /
`correct-horse-battery`.

```bash
python scripts/probe_providers.py
```
Which of your API keys actually work, and how fast each model is. Prints no keys.

```bash
python scripts/check_postgres.py --from-env NEON_DATABASE_URL
```
Creates the whole schema on the production Postgres, tests it, and drops it again.

---

## Looking under the hood

**Interactive API docs:** http://127.0.0.1:8000/docs

Every endpoint, with the request and response shapes, and a *Try it out* button. Generated from
the code, so it cannot drift out of date.

**The database:** `workspace.db` in the project root, plain SQLite. Open it with
[DB Browser for SQLite](https://sqlitebrowser.org/) to see all 12 tables.

**Start fresh:** stop the API, delete `workspace.db`, restart. A new empty database is created
automatically.

---

## If something looks wrong

| What you see | What it is |
|---|---|
| Sign-in page keeps returning | The API is not running, or is on a different port. Check terminal 1 |
| "Something went wrong" on every action | Terminal 1 has the real error |
| Chat fails with a 502 | The model provider refused — usually a rate limit. Terminal 1 says which |
| Documents stay "Processing" | Embedding is rate limited. It still becomes searchable by keyword |
| "Daily embedding quota exhausted" | Google's free tier is 1,000/day. Search drops to keyword-only until it resets |
| A 429 with `Retry-After` | You hit the platform's own rate limit. Defaults: 10 logins/min, 120 API calls/min |
| Changed Python code, nothing happened | The API needs `--reload`, or a manual restart |
| Changed React code, nothing happened | Hard-refresh the browser (Ctrl+Shift+R) |
| First message after starting is slow | Expected once. Later messages are ~0.2s |

---

## Where things live

```
api/          the HTTP layer         — routes, auth, validation
services/     the actual logic       — chat, documents, memory, skills
db/models.py  the 12 tables
skills/       one file per skill     — add one here
web/src/      the React app
scripts/      verification, one per phase + benchmark.py
tests/        406 tests
```

Two rules the code follows, with tests behind them:

- nothing in `services/` imports FastAPI, so every service is testable without a server
- nothing in `web/src/` calls `fetch` except `lib/api.ts`

Both are asserted in [tests/test_architecture.py](tests/test_architecture.py), and each was
proved to fail by injecting the violation before being trusted.
