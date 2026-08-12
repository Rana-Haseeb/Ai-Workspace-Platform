# Performance Report

Eight measured areas. Every number below came out of
[`scripts/benchmark.py`](../scripts/benchmark.py) and is stored in
[`docs/performance.json`](performance.json). Nothing here is an estimate.

```bash
python scripts/benchmark.py              # everything
python scripts/benchmark.py --offline    # skip the two that call a provider
```

**Method.** Each measurement runs a discarded warm-up pass, then 3–50 timed repeats reported as
a distribution rather than a mean. That is not decoration: Phase 3 recorded a "20.7 second chat
response" that turned out to be 18 seconds of `langchain_openai` importing. A single timing
measures your imports; a p50 and a p95 measure your software.

**Environment.** SQLite in-memory, Python 3.13, Windows, single process. Groq
`openai/gpt-oss-120b` for the model, Google `gemini-embedding-001` at 768d for embeddings.

---

## 1. HTTP round trip

No model, no embedding — the framework, the database and JSON serialisation.

| Operation | p50 | p95 | n |
|---|---|---|---|
| Health probe | **4.87 ms** | 5.92 ms | 20 |
| List workspaces (authenticated) | **9.23 ms** | 13.26 ms | 20 |
| Workspace detail + settings | **12.21 ms** | 14.51 ms | 20 |

**Reading.** The ~4 ms gap between the health probe and an authenticated list is the auth
middleware plus a user lookup. Everything is comfortably inside a 16 ms frame budget, so the
API is not what a user will perceive.

## 2. Authentication

| Operation | p50 | p95 | n |
|---|---|---|---|
| argon2id hash | **75.25 ms** | 87.97 ms | 10 |
| argon2id verify | **69.20 ms** | 79.17 ms | 10 |
| Issue a JWT | **0.03 ms** | 0.04 ms | 50 |

**Reading.** Login is ~70 ms and that is the design working, not a problem to optimise: the cost
is what makes offline guessing expensive. At ~14 verifications per second per core it is also the
most expensive endpoint in the system, which is exactly why it has the tightest rate limit.

Issuing a token is 2,300× cheaper than verifying a password — worth knowing, because it means
session length trades directly against login cost.

## 3. Database

| Operation | p50 | p95 | n |
|---|---|---|---|
| Read a 200-message transcript | **3.19 ms** | 47.58 ms | 20 |
| Dashboard aggregate (full HTTP) | **18.15 ms** | 19.25 ms | 20 |

**Reading — and the one number here worth staring at.** The transcript read has a p50 of 3 ms and
a p95 of 47 ms, a **15× spread**. That is not query cost; it is SQLite plus Python garbage
collection on a 200-row materialisation. It is called out rather than averaged away because the
mean (7 ms) would hide it entirely.

The dashboard aggregate is the most database-heavy endpoint and still under 20 ms, because the
counting happens in SQL rather than in Python.

## 4. Document processing

A 31 KB Markdown document — a realistic report.

| Stage | p50 | p95 | n |
|---|---|---|---|
| Extract text | **2.39 ms** | 2.64 ms | 10 |
| Chunk at 800 chars | **0.11 ms** | 0.12 ms | 10 |

Produced **50 chunks**.

**Reading.** Local processing is free — 2.5 ms for 31 KB. Ingestion time is therefore entirely
embedding time (§7), which is a network cost, not a compute one. That is why ingestion runs as a
background task: the expensive part is waiting on someone else's API.

## 5. Retrieval

| Operation | p50 | p95 | n |
|---|---|---|---|
| BM25 over 50 chunks (via the database) | **5.19 ms** | 8.15 ms | 20 |

Measured through the real `retrieve()` path with rows in a real table, not a list comprehension
in memory.

**The known scaling limit.** BM25 here rebuilds its index from every chunk in the workspace on
every query, and vector search loads every vector in the workspace per query. Both are linear.
At 50 chunks that is 5 ms; at 50,000 chunks it is not 5 ms, and the honest statement is that this
has been measured at one size only. The `VectorStore` interface exists so pgvector can replace
the scan without touching callers.

## 6. Memory ranking

| Operation | p50 | p95 | n |
|---|---|---|---|
| Rank 500 memories by importance × recency | **1.26 ms** | 1.35 ms | 20 |

**Reading.** 2.5 µs per memory. Ranking is pure arithmetic over rows already loaded, and with the
context cap at 8 items this will not be a bottleneck at any realistic size.

## 7. Embeddings — measured, then blocked

| Operation | Result |
|---|---|
| Embed one query (Google, 768d) | **~1.4 s** (n=1, observational) |
| Controlled run (n=3) | **blocked — daily quota exhausted** |

**Stated honestly:** the controlled measurement did not complete. The free tier allows 1,000
embedding requests **per day**, and the day's allowance was spent by the evaluation, the
experiments and this benchmark. The single 1.4 s sample is a real observation from a real call,
recorded with n=1 rather than padded into a distribution.

Real ingestion logs from the same day, as corroboration, not as a benchmark: 2 chunks in 1.75 s,
3 chunks in 0.84 s, 2 chunks in 1.68 s.

**The defect this exposed.** Google returns `retryDelay: 58s` on a 429 *even when the exhausted
quota is daily*. The backoff honoured that blindly, so an exhausted daily quota produced five
retries over roughly **four minutes** before failing — for something that resets tomorrow.

Fixed by reading the `quotaId`: a quota containing `PerDay` fails immediately, anything else
still retries, and an unrecognisable body still retries (failing safe).

| | Before | After |
|---|---|---|
| Call against an exhausted daily quota | ~240 s | **0.59 s** |

This is why the test suite hung: it was making real embedding calls, and each one sat in that
retry loop. Both problems are fixed — the suite no longer touches the network at all, and the
retry no longer waits out a quota that will not move.

## 8. Chat completion

| Operation | p50 | p95 | n |
|---|---|---|---|
| Model round trip, `gpt-oss-120b` via Groq | **495 ms** | 685 ms | 3 |

Warm-up discarded. A short question, a one-sentence answer.

**Reading.** Half a second is the entire user-perceived cost of a chat turn: everything the
platform does around it — retrieval at 5 ms, memory ranking at 1 ms, persistence at 3 ms — sums
to under 1% of the request. **The model is the budget.** Optimising the Python here would be
optimising noise.

This is also the number to hold against Phase 8's evaluation mean of 4,557 ms. That figure covers
long answers over larger contexts under back-to-back load; this one is a warm single turn. Both
are real, and they measure different things.

---

## Where the time actually goes

For one chat turn with document grounding, warm:

| Stage | Time | Share |
|---|---|---|
| Retrieval (BM25) | 5 ms | ~1% |
| Memory ranking | 1 ms | <1% |
| Prompt assembly | <1 ms | <1% |
| Persistence | 3 ms | <1% |
| **Model call** | **495 ms** | **~97%** |

Ingestion is the opposite shape: parsing and chunking cost 2.5 ms for 31 KB, while embedding
those 50 chunks costs seconds. Both paths are dominated by somebody else's API, which is the
single most useful thing this report says.

---

## Limitations

- **SQLite in-memory, not Postgres.** Every database number is a floor. Neon adds network
  latency per query; the schema was verified against real Postgres in Phase 4, but not timed.
- **Single process, no concurrency.** These are latencies under no load, not throughput. Nothing
  here predicts behaviour at 50 concurrent users.
- **Small n on the live measurements** (3 for chat, 1 for embeddings) because free-tier quota is
  finite. Stated at every table rather than hidden.
- **One machine, one run.** No variance across environments.
- **The 47 ms p95 on the transcript read is not explained**, only observed. Profiling it would
  need a proper sampling profiler, which this report does not have.
