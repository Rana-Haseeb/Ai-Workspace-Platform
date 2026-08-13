# Builder Journal

Week 5 · AI Workspace Platform · eleven phases, each with a gate that prints real output.

Not a changelog — the git history is the changelog. This is what actually went wrong, and what
changed in how I work as a result.

---

## The rhythm

Every phase followed the same loop: **build → verify with real output → find bugs → fix → prove
the fix**. Each phase ends with a `verify_phaseN.py` that prints evidence rather than a green
tick, and nothing was called done until that output passed.

That structure is the reason most of the interesting bugs below were found at all. They were
found by scripts written to *look*, not by tests written to pass.

---

## Five mistakes worth recording

### 1. I leaked two live API keys into a transcript

**Phase 0.** I wrote a masking command that assumed `KEY=value` while the file used `key: value`.
Both a Groq and a Google key printed in full.

I flagged it immediately and recommended rotation, and have repeated that at every phase since.
The lesson is not "be careful with sed" — it is that **a masking routine is security code and
needs a test like any other**. In Phase 9 I found the same class of bug still live: the provider
probe redacted `GROQ_API_KEY` *by name*, so adding `GROQ_API_KEY_2` silently created a hole. It
now reads the key names from the provider registry, and I proved the redaction works by feeding
it each real key inside a fake error.

### 2. I claimed a model was "pathologically slow". It was my own imports.

**Phase 3.** I measured `gpt-oss-120b` at 20.3 seconds and wrote that it was unusable.

It was false. `langchain_openai` takes ~18 seconds to import the first time, and whichever model
ran first paid it. All three models are sub-second warm. Importing at application startup took
the first user message from 20.7s to 2.5s.

**What changed:** every measurement I take now discards a warm-up pass and reports a distribution.
A single timing measures your imports. It came up again in Phase 9, and I recognised the shape
immediately: a 26.9-second first sample sitting next to four ~2-second ones. That number is in
the report with a footnote rather than deleted, because a number removed silently is worse than
one explained.

### 3. Reading a page is not testing a page

**Phase 7.** The user asked why nothing scrolled. Three routes were unreachable below the fold —
the Settings delete button simply could not be reached.

My checks had missed it because I read text via `innerText`, which returns content whether or not
a human can get to it. **I had never actually scrolled.** I fixed the shell, wrote
`check_frontend_rules.js`, and — the part that mattered — proved the new guard *failed* on the
old markup before trusting it.

That habit has caught things ever since. In Phase 9 I injected a `fastapi` import into a service,
a raw `fetch` into a component, and removed an ownership check from a router, purely to watch
three new tests fail. In Phase 8 I injected three corrupted result files for the same reason. One
of my own checks passed **vacuously** on an empty list (`0 == 0`) and I only found it because I
tried to break it.

### 4. The most confident claim in the project was wrong

**Phase 9.** The evaluation reported that document-borne prompt injection had been resisted. I
wrote that up as a headline result.

Tested directly, the injection **succeeded on both models** — every question came back
`PINEAPPLE`. The evaluation had almost certainly never retrieved the poisoned chunk. **An attack
that is never delivered is not an attack that was defeated.**

The tell had been visible the whole time and I read past it: the scenario was recorded as having
"missed the figure" in that same document. That is not a retrieval miss to shrug at — it is
evidence the chunk was never in context.

The root cause was structural: untrusted document text was going into the `system` message. The
gate now proves the payload is retrievable *before* testing whether it was obeyed, and the wrong
claim is left standing in the README with a correction attached rather than quietly edited away.

### 5. Half of every document was never reaching the model

Found while investigating the injection. `context_block()` fed the model a 400-character display
snippet while chunks are 800 characters. Every fact in the back half of a chunk was parsed,
embedded, indexed, scored and **cited** — and never sent.

Asked about a document plainly saying *"closed 312 tickets this quarter"*, the platform said the
excerpts did not mention it.

This was running underneath the entire evaluation, which means the published 86.4% is a floor.
It may also contaminate the chunk-size experiment: 300-character chunks lose nothing to a
400-character cap while 1600-character chunks lose three quarters, so part of "smaller is better"
could be this bug rather than embedding dilution. That experiment is flagged for re-running
rather than quietly kept.

**The uncomfortable part:** citations were correct throughout. The UI looked right, the sources
were right, only the content was short. Nothing in a passing test suite could see it.

---

## What I would tell myself at the start

**Write the test that fails first, even for infrastructure.** Four of the five worst defects here
were invisible to a passing suite. The suite was not weak — it was measuring things that worked.

**Assert your preconditions inside the test.** A security scenario that never delivers its
payload passes. A results check that runs on an empty list passes. Both did.

**Ask what else is inside a number.** Two figures in this project were wrong because of what
surrounded them: 18 seconds of library import inside a "slow model", and a four-minute stall that
was a retry loop waiting out a quota which resets tomorrow.

**Configuration is a promise.** `RATE_LIMIT_PER_MINUTE` existed, was documented, and was read by
nothing. Anyone reading it would have believed login was defended.

**Report the negative results.** The detailed system prompt bought exactly 0% for ~70 tokens a
turn. More retrieved context halved accuracy. Those are the findings that changed what I believe,
and both would have been easy to leave out.

---

## Where it stands

389 tests, eleven phase gates, 44 evaluation scenarios and six experiments — all with real output
in the repository. Three experiment results contradict the shipped defaults and are deliberately
left unchanged, because one run over four documents is not enough evidence to reconfigure a
platform.

The number I would most like to have is the evaluation re-run with the truncation fixed. It needs
an embedding allowance that resets tomorrow, and a partial re-run would not be comparable — so it
is written down as outstanding rather than estimated.
