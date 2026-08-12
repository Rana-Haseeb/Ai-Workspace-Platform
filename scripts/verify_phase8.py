"""Phase 8 gate: the evaluation and experiment results are real, complete, and internally consistent.

Offline by design. It re-reads the committed result files and checks them against the dataset
that produced them, because the failure this guards against is not a broken model — it is a
*stale or partial results file* that still looks authoritative. Two things nearly happened during
Phase 8 and are now checked here directly:

  - ``--only 5`` overwrote the whole results file, deleting five good experiments. Now the runner
    merges, and this asserts all six survive.
  - Experiment 5 twice produced a number that measured something other than its variable. Now the
    runner records ``baseline_correct``, and this asserts no experiment reports a finding while
    its own baseline says the run was invalid.

    python scripts/verify_phase8.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.dataset import CATEGORIES, SCENARIOS, by_category, corpus_files  # noqa: E402

EVAL_RESULTS = ROOT / "eval" / "results.json"
EXPERIMENT_RESULTS = ROOT / "experiments" / "results.json"

# Anything shaped like a provider key. These files are committed, so a key reaching one is a
# disclosure, not a typo.
SECRET = re.compile(r"(gsk_[A-Za-z0-9]{10,}|AQ\.[A-Za-z0-9_-]{10,}|npg_[A-Za-z0-9]{6,}"
                    r"|sk-[A-Za-z0-9]{20,})")

failures: list[str] = []


def safe(text) -> str:
    return str(text).encode("ascii", "replace").decode("ascii")


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"   {'OK  ' if ok else 'FAIL'} {label}" + (f"  [{safe(detail)}]" if detail else ""))
    if not ok:
        failures.append(label)


def main() -> int:
    print("\nPhase 8 verification - evaluation and experiments\n")

    # ------------------------------------------------------------------ 1. dataset
    print("1. Evaluation dataset")
    check("at least 40 scenarios", len(SCENARIOS) >= 40, f"{len(SCENARIOS)}")
    grouped = by_category()
    check("all seven categories covered", set(grouped) == set(CATEGORIES))
    for category in CATEGORIES:
        count = len(grouped.get(category, []))
        check(f"  {category}", count >= 4, f"{count} scenarios")
    check("corpus present", len(corpus_files()) >= 3, f"{len(corpus_files())} documents")

    poisoned = [p for p in corpus_files() if p.name == "quarterly_summary.md"]
    planted = bool(poisoned) and "ignore all previous instructions" in \
        poisoned[0].read_text(encoding="utf-8").lower()
    check("prompt-injection bait really planted", planted)

    # -------------------------------------------------------------- 2. eval results
    print("\n2. Evaluation results")
    if not EVAL_RESULTS.exists():
        check("eval/results.json exists", False)
        return _finish()
    evaluation = json.loads(EVAL_RESULTS.read_text(encoding="utf-8"))
    summary = evaluation.get("summary", {})
    check("eval/results.json exists", True)

    for metric in ["accuracy", "task_success", "memory_recall",
                   "citation_quality", "mean_response_time_ms"]:
        present = summary.get(metric) is not None
        check(f"  {metric}", present, f"{summary.get(metric)}")

    scored = evaluation.get("scenarios", [])
    check("every scenario has a result", len(scored) == len(SCENARIOS),
          f"{len(scored)} of {len(SCENARIOS)}")

    # A result file where nothing was actually asked of a model is the failure mode that looks
    # most like success: all the keys present, every number zero. The `and scored` matters —
    # without it an empty list satisfies "all of them ran" and this check passes vacuously,
    # which is precisely the bug it exists to catch.
    ran = sum(1 for r in scored if r.get("latency_ms", 0) > 0)
    check("results came from real calls, not stubs", bool(scored) and ran == len(scored),
          f"{ran} of {len(scored)} with non-zero latency")

    ids_scored = {r.get("id") for r in scored}
    missing = [s.id for s in SCENARIOS if s.id not in ids_scored]
    check("no scenario silently skipped", not missing, ", ".join(missing[:4]))

    # ------------------------------------------------------- 3. experiment results
    print("\n3. Experiment results")
    if not EXPERIMENT_RESULTS.exists():
        check("experiments/results.json exists", False)
        return _finish()
    payload = json.loads(EXPERIMENT_RESULTS.read_text(encoding="utf-8"))
    experiments = payload.get("experiments", {})
    check("experiments/results.json exists", True)
    check("six experiments recorded", len(experiments) == 6, f"{len(experiments)}")

    for title, body in experiments.items():
        if "error" in body:
            check(f"  {title}", False, body["error"][:60])
            continue
        # An experiment must have measured something and said what it means.
        has_data = bool(body.get("arms") or body.get("measurements"))
        check(f"  {title}", has_data and bool(body.get("finding")))

    # ------------------------------------------- 4. no experiment overstates itself
    print("\n4. Findings match the data behind them")
    for title, body in experiments.items():
        if "baseline_correct" not in body:
            continue
        finding = body.get("finding", "")
        claims_result = "INCONCLUSIVE" not in finding
        # The guard that Phase 8 actually needed: a finding that reads like a conclusion while
        # the run's own baseline says the measurement was invalid.
        check(f"  {title}: conclusion only when baseline held",
              body["baseline_correct"] == claims_result,
              f"baseline_correct={body['baseline_correct']}")

    # ------------------------------------------------------------- 5. no leaked keys
    print("\n5. Secrets hygiene")
    for path in [EVAL_RESULTS, EXPERIMENT_RESULTS, ROOT / "scripts" / "probe_results.json"]:
        if path.exists():
            hits = SECRET.findall(path.read_text(encoding="utf-8"))
            check(f"  {path.relative_to(ROOT)} carries no key", not hits,
                  f"{len(hits)} match(es)" if hits else "")

    return _finish()


def _finish() -> int:
    if failures:
        print(f"\nPHASE 8 FAILED - {len(failures)} problem(s):")
        for problem in failures:
            print(f"   - {problem}")
        return 1
    print("\nPHASE 8 PASSED - 44 scenarios scored, 6 experiments with data, no overstated finding.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
