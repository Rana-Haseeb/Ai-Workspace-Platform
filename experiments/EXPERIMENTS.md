# Experiments

Six experiments, each isolating one variable. Every arm runs at temperature 0.0 against a fresh
platform instance, so the only thing differing between arms is the variable under test.

```bash
python experiments/run_experiments.py
```

Raw output: [`experiments/results.json`](results.json). Experiments 1–4 and 6 ran together in 1,253
seconds; Experiment 5 was re-run separately in 69 seconds once a second Groq organisation gave it
the quota it needed, so each entry in the JSON carries its own `run_at`.

**All six completed with real results.** Experiment 5 took three attempts to become valid — the
first two are documented in its section rather than quietly dropped.

---

## 1. Memory enabled vs disabled

*Does long-term memory change answers, or is it decoration?*

| Arm | Accuracy | Mean score |
|---|---|---|
| **Memory on** | **100%** | 1.00 |
| Memory off | **0%** | 0.08 |

**Finding.** The cleanest result in the set. With memory disabled the platform cannot answer a
single memory-dependent question; with it enabled, all six. The gap is total, which also confirms
the memory scenarios genuinely require recall rather than letting the model guess from context.

---

## 2. Short prompt vs detailed prompt

*Is a long system prompt worth the tokens it costs, on every single turn?*

| Arm | Length | Accuracy | Mean score | Latency |
|---|---|---|---|---|
| Short | 28 chars | 60% | 0.82 | 8,537 ms |
| Detailed | 309 chars | 60% | 0.84 | 7,079 ms |

**Finding — a negative result, and worth reporting as one.** The detailed prompt bought
**+0% accuracy** for ~70 extra tokens on every turn. Mean score rose by 0.02, which is inside
the noise of a ten-scenario sample.

The instinct to write longer, more careful system prompts is not supported here. On a corpus this
size the grounding instruction attached to the excerpts is already doing the work the detailed
prompt was meant to do, and repeating it costs tokens for nothing.

---

## 3. Different models

*Which model should the deployment default to?*

| Model | Accuracy | Mean score | Latency |
|---|---|---|---|
| **`openai/gpt-oss-120b`** | **77%** | **0.90** | 8,541 ms |
| `llama-3.3-70b-versatile` | 69% | 0.86 | 9,094 ms |
| `openai/gpt-oss-20b` | 62% | 0.78 | 8,278 ms |

**Finding.** `gpt-oss-120b` is both the most accurate **and** faster than the current default.
`gpt-oss-20b` is fastest but clearly worst.

**This contradicts the current configuration.** The deployment default is
`llama-3.3-70b-versatile`, chosen in Phase 3 on raw speed. On accuracy it is 8 points behind, at
no latency saving. The per-workspace model setting means a user can still trade back, but the
default should follow accuracy: a wrong answer delivered quickly is still wrong.

---

## 4. Small vs large context

*Does feeding more retrieved excerpts improve answers?*

| Arm | Accuracy | Mean score | Latency |
|---|---|---|---|
| **`top_k=2`** | 60% | **0.84** | 10,375 ms |
| `top_k=6` | 60% | 0.77 | 8,388 ms |
| `top_k=12` | **30%** | **0.42** | 5,534 ms |

**Finding — the most actionable result here.** More context is not merely unhelpful, it is
actively harmful. Doubling from 6 to 12 excerpts **halved accuracy**, from 60% to 30%.

The mechanism is visible in the evaluation failures: with twelve excerpts the relevant passage
competes with eleven near-misses, and the model picks a plausible neighbour. That is exactly what
produced the worst evaluation failure — `doc-03`, where the platform reported Weaviate's score of
6 as pgvector's, having been handed both.

The current default of `top_k=6` sits at the same accuracy as 2 but a lower mean score. On this
corpus, **2 is the better setting**.

---

## 5. Conversation length

*Does accuracy or latency degrade as a conversation grows?*

The same question — *"how many milliseconds did pgvector take with an HNSW index?"* — is asked
repeatedly in one conversation, with three filler turns between each probe. The answer is a fixed
fact from the corpus, so any change in correctness is a property of the conversation, not the
question.

| Messages in history | Answer | Latency |
|---|---|---|
| 2 | correct | 26,891 ms † |
| 10 | correct | 2,132 ms |
| 18 | correct | 2,193 ms |
| 26 | correct | 2,640 ms |
| 34 | correct | 3,313 ms |

† **Not a latency measurement.** The first call in a fresh process pays the one-off
`langchain_openai` import, ~18 s of it. The production server pays this at startup instead
(§7.4), so no user ever sees it. It is left in the table rather than deleted, because a number
removed silently is worse than a number explained.

**Finding.** Accuracy held at **5 of 5** across a transcript growing from 2 to 34 messages —
a 17× growth with no degradation. History is trimmed to the last 20 messages
([`services/chat_service.py:32`](../services/chat_service.py)), so from message 20 onward the
prompt is a **constant** size: cost per turn stops growing, by construction rather than by luck.

**What this does *not* establish.** The warm latencies drift upward — 2,132 → 3,313 ms — and
2,640 and 3,313 both sit *past* the trim point, where the prompt is provably the same size. So
that drift is not prompt growth. It is one unrepeated run on a shared free tier, and with no
variance estimate a 1.2-second spread is not distinguishable from load. **Reported as observed,
not as a trend.** Isolating it would need repeated runs at fixed history depths.

The experiment took two earlier attempts, both invalid, both recorded rather than dressed up:

- **Attempt one** probed for pgvector's maximum indexed dimension. The answer is in the corpus,
  but retrieval never surfaces that chunk — verified against the search endpoint. Every probe was
  wrong from turn one, so it measured a retrieval gap, not conversation length.
- **Attempt two** used the verified-retrievable probe above, but by then the evaluation plus the
  other five experiments had exhausted the Groq free tier: every probe returned HTTP 502.

Both failures are the same shape — *the baseline was broken for a reason unrelated to the
variable under test*. The harness now checks `baseline_correct` and reports `INCONCLUSIVE` rather
than a number, which is what kept a meaningless result out of this document twice.

---

## 6. Chunk size comparison

*How big should a chunk be?*

| Arm | Chunks created | Accuracy | Mean score | Latency |
|---|---|---|---|---|
| **300 chars** | 22 | **60%** | **0.72** | 6,899 ms |
| 800 chars *(current default)* | 8 | 50% | 0.62 | 5,887 ms |
| 1600 chars | 4 | 30% | 0.57 | 6,023 ms |

**Finding.** Smaller is better on this corpus, and the trend is monotonic: halving the chunk size
from 1600 to 800 gained 20 points, and halving again gained another 10.

The mechanism is embedding dilution. A 1600-character chunk covering four topics produces a
vector that is the average of four things and therefore close to none of them; a 300-character
chunk about one thing matches that thing strongly.

The counter-pressure is real but did not bite here: small chunks can sever a fact from the
sentence that qualifies it. The 120-character overlap is what keeps that in check.

**This contradicts the current default of 800.** On a corpus of short, dense reference documents,
300 would be the better setting.

---

## What these experiments changed

Three results contradict decisions made earlier in the build:

| Setting | Current | Experiment says | Why it was set that way |
|---|---|---|---|
| Default model | `llama-3.3-70b` | `gpt-oss-120b` | Chosen on raw latency in Phase 3, before accuracy was measurable |
| `RETRIEVAL_TOP_K` | 6 | 2 | Picked as a conventional default; never measured |
| `CHUNK_SIZE` | 800 | 300 | Picked as a conventional default; never measured |

They are **left unchanged in the committed configuration**, deliberately. Each rests on a single
run over a four-document corpus and ten document scenarios, where one flipped result moves
accuracy by 10 points. Changing three defaults on that evidence would be trading a guess for a
slightly better-informed guess.

What the experiments have earned is a *documented reason to test them properly* — on a larger
corpus, with repeated runs — which is the honest next step rather than a configuration change
this evidence cannot support.

---

## Limitations

- **One run per arm.** No variance estimate, so small differences are not distinguishable from
  noise. Only Experiments 1, 4 and 6 show gaps large enough to be confident about — and
  Experiment 5's latency drift is exactly the kind of small difference this limitation forbids
  drawing a conclusion from.
- **Ten document scenarios per arm.** One flipped result is 10 percentage points.
- **A four-document corpus.** Retrieval behaviour at four documents does not predict four hundred,
  and Experiments 4 and 6 are precisely the ones most sensitive to corpus size.
- **Experiment 5 tests retention, not reasoning.** It re-asks one factual question. A conversation
  that *builds* on its own earlier answers could degrade in ways a fixed probe cannot see.
- **Free-tier quota is a real constraint.** The full suite plus the evaluation exhausts one Groq
  organisation's daily allowance — that is what blocked Experiment 5 twice. The fix was a second
  organisation in the failover chain, not a smaller experiment.
