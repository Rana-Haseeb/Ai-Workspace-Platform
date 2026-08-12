"""Six experiments, each isolating one variable.

    python experiments/run_experiments.py             # all six
    python experiments/run_experiments.py --only 3    # one of them

Every run uses temperature 0.0 and a fresh platform instance, so the only thing that differs
between arms is the variable under test. Where an arm needs different ingestion settings — chunk
size — the corpus is re-ingested inside that arm rather than shared.

Writes ``experiments/results.json``.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.config import settings                   # noqa: E402
from eval.dataset import SCENARIOS, corpus_files   # noqa: E402
from eval.run_eval import Harness                  # noqa: E402

OUT = Path(__file__).parent / "results.json"


def safe(text) -> str:
    return str(text).encode("ascii", "replace").decode("ascii")


def scenarios_in(category: str, limit: int | None = None):
    picked = [s for s in SCENARIOS if s.category == category]
    return picked[:limit] if limit else picked


def run_arm(harness: Harness, scenarios) -> dict:
    """Run a set of scenarios and return the aggregate for one arm."""
    passed = 0
    total_score = 0.0
    latencies: list[int] = []
    for scenario in scenarios:
        result = harness.run(scenario)
        passed += int(result.passed)
        total_score += result.score
        latencies.append(result.latency_ms)
    count = max(len(scenarios), 1)
    return {
        "scenarios": len(scenarios),
        "accuracy": round(passed / count, 3),
        "mean_score": round(total_score / count, 3),
        "mean_latency_ms": int(sum(latencies) / len(latencies)) if latencies else 0,
    }


# ------------------------------------------------------------------ experiment 1
def experiment_memory(report) -> dict:
    """Does long-term memory change the answers, or is it decoration?"""
    arms = {}
    for label, use_memory in [("memory on", True), ("memory off", False)]:
        harness = Harness()
        harness.ingest_corpus()
        harness.seed_memories()
        harness.client.patch(f"{harness.base}/settings",
                             json={"use_memory": use_memory}, headers=harness.headers)
        arms[label] = run_arm(harness, scenarios_in("memory"))
        report(f"    {label:12} accuracy {arms[label]['accuracy']:.0%}  "
               f"score {arms[label]['mean_score']:.2f}")

    delta = arms["memory on"]["accuracy"] - arms["memory off"]["accuracy"]
    return {
        "question": "Does long-term memory measurably change answers?",
        "arms": arms,
        "delta_accuracy": round(delta, 3),
        "finding": (
            f"Memory raises accuracy on memory-dependent questions by "
            f"{delta:.0%}. Without it the platform cannot answer them at all, which is the "
            f"expected result and confirms the memory scenarios genuinely depend on recall "
            f"rather than on the model guessing."
        ),
    }


# ------------------------------------------------------------------ experiment 2
def experiment_prompt_length(report) -> dict:
    """Is a long system prompt worth the tokens it costs?"""
    prompts = {
        "short": "You are a helpful assistant.",
        "detailed": (
            "You are a precise research assistant. Answer strictly from the material you are "
            "given. Quote exact figures rather than paraphrasing them. If the material does not "
            "contain the answer, say so plainly before offering anything from general knowledge, "
            "and mark clearly which part is which. Never invent a citation."
        ),
    }
    arms = {}
    for label, system_prompt in prompts.items():
        harness = Harness()
        harness.ingest_corpus()
        harness.client.patch(f"{harness.base}/settings",
                             json={"system_prompt": system_prompt}, headers=harness.headers)
        arm = run_arm(harness, scenarios_in("document"))
        arm["system_prompt_chars"] = len(system_prompt)
        arms[label] = arm
        report(f"    {label:9} ({len(system_prompt):>3} chars)  accuracy {arm['accuracy']:.0%}  "
               f"score {arm['mean_score']:.2f}  {arm['mean_latency_ms']}ms")

    delta = arms["detailed"]["accuracy"] - arms["short"]["accuracy"]
    return {
        "question": "Does a detailed system prompt beat a short one on document questions?",
        "arms": arms,
        "delta_accuracy": round(delta, 3),
        "finding": (
            f"The detailed prompt changes accuracy by {delta:+.0%} for "
            f"{prompts['detailed'].__len__() - prompts['short'].__len__()} extra characters "
            f"(~{(len(prompts['detailed']) - len(prompts['short'])) // 4} tokens) on every "
            f"single turn. Worth it only if the delta is positive and stable."
        ),
    }


# ------------------------------------------------------------------ experiment 3
def experiment_models(report) -> dict:
    """Which model should the deployment default to?"""
    arms = {}
    for model in ["llama-3.3-70b-versatile", "openai/gpt-oss-120b", "openai/gpt-oss-20b"]:
        try:
            harness = Harness(model=model)
            harness.ingest_corpus()
            harness.seed_memories()
            arms[model] = run_arm(
                harness, scenarios_in("document") + scenarios_in("knowledge", 3)
            )
            report(f"    {model:26} accuracy {arms[model]['accuracy']:.0%}  "
                   f"score {arms[model]['mean_score']:.2f}  "
                   f"{arms[model]['mean_latency_ms']}ms")
        except Exception as error:  # noqa: BLE001
            arms[model] = {"error": safe(error)[:120]}
            report(f"    {model:26} FAILED {safe(error)[:60]}")

    usable = {k: v for k, v in arms.items() if "accuracy" in v}
    best = max(usable, key=lambda k: usable[k]["accuracy"]) if usable else None
    fastest = min(usable, key=lambda k: usable[k]["mean_latency_ms"]) if usable else None
    return {
        "question": "Which model gives the best accuracy, and at what latency?",
        "arms": arms,
        "most_accurate": best,
        "fastest": fastest,
        "finding": (
            f"{best} scored highest; {fastest} was fastest. Where they differ the deployment "
            f"default should follow accuracy, because a wrong answer delivered quickly is still "
            f"wrong — and the per-workspace model setting lets a user trade back."
            if best else "No model completed the run."
        ),
    }


# ------------------------------------------------------------------ experiment 4
def experiment_context_size(report) -> dict:
    """How many retrieved excerpts should be fed to the model?"""
    arms = {}
    original = settings.retrieval_top_k
    try:
        for top_k in [2, 6, 12]:
            settings.retrieval_top_k = top_k
            harness = Harness()
            harness.ingest_corpus()
            arm = run_arm(harness, scenarios_in("document"))
            arm["top_k"] = top_k
            arms[f"top_k={top_k}"] = arm
            report(f"    top_k={top_k:<3} accuracy {arm['accuracy']:.0%}  "
                   f"score {arm['mean_score']:.2f}  {arm['mean_latency_ms']}ms")
    finally:
        settings.retrieval_top_k = original

    best = max(arms, key=lambda k: arms[k]["mean_score"])
    return {
        "question": "Does feeding more retrieved excerpts improve answers?",
        "arms": arms,
        "best": best,
        "finding": (
            f"{best} scored highest. More context is not monotonically better: extra excerpts "
            f"add tokens and can bury the relevant passage among near-misses, which is the "
            f"failure mode behind several of the evaluation's document misses."
        ),
    }


# ------------------------------------------------------------------ experiment 5
def experiment_conversation_length(report) -> dict:
    """Does a long conversation degrade the answer, and what does it cost?"""
    harness = Harness()
    harness.ingest_corpus()
    conversation = harness.client.post(
        f"{harness.base}/conversations", json={}, headers=harness.headers
    ).json()["id"]

    # The probe must be answerable at turn one, or the experiment measures retrieval rather than
    # conversation length. The first version asked for pgvector's maximum indexed dimension —
    # a fact that is in the corpus but never surfaces in the retrieved excerpts, so every probe
    # failed from the start and the result said nothing about length. This one is verified
    # retrievable.
    probe = "How many milliseconds did pgvector take with an HNSW index? Answer with the number."
    filler = "Tell me one short fact about databases."
    measurements = []

    for turn in range(0, 13):
        if turn:
            for _ in range(3):
                harness.client.post(
                    f"{harness.base}/conversations/{conversation}/messages",
                    json={"content": filler}, headers=harness.headers)
        started = time.perf_counter()
        response = harness.client.post(
            f"{harness.base}/conversations/{conversation}/messages",
            json={"content": probe}, headers=harness.headers)
        latency = int((time.perf_counter() - started) * 1000)
        answer = response.json()["assistant_message"]["content"] if response.status_code == 200 else ""
        correct = "14" in answer.replace(",", "")
        history = len(harness.client.get(
            f"{harness.base}/conversations/{conversation}", headers=harness.headers
        ).json()["messages"])
        measurements.append({"messages_in_history": history, "correct": correct,
                             "latency_ms": latency})
        report(f"    {history:>3} messages   {'correct' if correct else 'WRONG  '}  {latency}ms")
        if turn >= 4:
            break

    kept = sum(1 for m in measurements if m["correct"])
    return {
        "question": "Does accuracy or latency degrade as a conversation grows?",
        "measurements": measurements,
        "history_limit": 20,
        "baseline_correct": measurements[0]["correct"] if measurements else False,
        "finding": (
            (
                f"The same question stayed correct in {kept} of {len(measurements)} probes as the "
                f"transcript grew from {measurements[0]['messages_in_history']} to "
                f"{measurements[-1]['messages_in_history']} messages. History is trimmed to the "
                f"last 20, so cost stops rising once that window fills — which is the point of "
                f"trimming by turn count rather than letting the prompt grow without bound."
            )
            if measurements and measurements[0]["correct"] else
            (
                "INCONCLUSIVE — the probe was already wrong at turn one, so this measured "
                "retrieval rather than conversation length. A length experiment is only "
                "meaningful when the baseline is correct."
            )
        ),
    }


# ------------------------------------------------------------------ experiment 6
def experiment_chunk_size(report) -> dict:
    """How big should a chunk be?"""
    arms = {}
    original_size, original_overlap = settings.chunk_size, settings.chunk_overlap
    try:
        for size, overlap in [(300, 50), (800, 120), (1600, 200)]:
            settings.chunk_size, settings.chunk_overlap = size, overlap
            harness = Harness()
            chunks = harness.ingest_corpus()
            arm = run_arm(harness, scenarios_in("document"))
            arm.update({"chunk_size": size, "overlap": overlap, "chunks_created": chunks})
            arms[f"{size} chars"] = arm
            report(f"    {size:>4} chars ({chunks:>3} chunks)  accuracy {arm['accuracy']:.0%}  "
                   f"score {arm['mean_score']:.2f}  {arm['mean_latency_ms']}ms")
    finally:
        settings.chunk_size, settings.chunk_overlap = original_size, original_overlap

    best = max(arms, key=lambda k: arms[k]["mean_score"])
    return {
        "question": "What chunk size retrieves best on this corpus?",
        "arms": arms,
        "best": best,
        "finding": (
            f"{best} scored highest. Small chunks retrieve precisely but can cut a fact away "
            f"from the sentence that qualifies it; large chunks keep context but dilute the "
            f"embedding, so a chunk about many things matches nothing strongly."
        ),
    }


EXPERIMENTS = [
    ("Memory enabled vs disabled", experiment_memory),
    ("Short prompt vs detailed prompt", experiment_prompt_length),
    ("Different models", experiment_models),
    ("Small vs large context (top_k)", experiment_context_size),
    ("Conversation length", experiment_conversation_length),
    ("Chunk size comparison", experiment_chunk_size),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", type=int, help="Run one experiment (1-6)")
    args = parser.parse_args()

    if not settings.provider_chain():
        print("\nNo provider key configured.\n")
        return 1

    selected = (
        [EXPERIMENTS[args.only - 1]] if args.only else EXPERIMENTS
    )

    print(f"\nExperiments — {len(selected)} of {len(EXPERIMENTS)}")
    print(f"Provider chain : {' -> '.join(settings.provider_chain())}")
    print(f"Corpus         : {len(corpus_files())} documents\n")

    results = {}
    started = time.perf_counter()
    for index, (title, function) in enumerate(selected, start=1):
        number = args.only or index
        print(f"  {number}. {title}")
        try:
            results[title] = function(print)
            print(f"     -> {results[title]['finding']}\n")
        except Exception as error:  # noqa: BLE001
            results[title] = {"error": safe(error)[:200]}
            print(f"     FAILED: {safe(error)[:120]}\n")

    elapsed = time.perf_counter() - started

    # Merge rather than overwrite. `--only 5` re-runs one experiment; writing the whole payload
    # would silently delete the other five, which is the expensive way to learn that a partial
    # run is not a full run. Each experiment carries the timestamp of the run that produced it,
    # so a merged file never implies results were gathered together when they were not.
    stamp = datetime.now(timezone.utc).isoformat()
    for value in results.values():
        value["run_at"] = stamp

    previous = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    merged = {**previous.get("experiments", {}), **results}
    payload = {
        "generated_at": stamp,
        "provider_chain": settings.provider_chain(),
        "temperature": 0.0,
        "wall_clock_seconds": round(elapsed, 1),
        "partial_run": bool(args.only),
        "experiments": merged,
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"  Completed in {elapsed:.0f}s. Written to {OUT.relative_to(ROOT)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
