"""How a scenario is scored.

Every check here is **deterministic**. No model judges another model's output, because an
LLM-as-judge introduces a second source of error that cannot be separated from the first: when
the score drops you cannot tell whether the platform got worse or the judge did.

The cost is that these checks are blunt. Keyword presence is not comprehension, and a correct
answer phrased unusually can score as a miss. That is a real limitation and it is stated in the
report rather than hidden — but a blunt measurement you can reproduce beats a subtle one you
cannot.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ScenarioResult:
    scenario_id: str
    category: str
    passed: bool
    score: float                      # 0.0-1.0, partial credit where the check allows it
    latency_ms: int
    checks: dict[str, bool] = field(default_factory=dict)
    answer: str = ""
    citations: list = field(default_factory=list)
    memory_used: list = field(default_factory=list)
    error: str | None = None


def _normalise(text: str) -> str:
    """Lowercase, collapse whitespace, strip thousands separators.

    ``2,300 users`` and ``2300 users`` are the same answer, and a scorer that disagrees is
    measuring formatting rather than correctness.
    """
    text = text.lower()
    text = re.sub(r"(\d),(\d)", r"\1\2", text)
    return re.sub(r"\s+", " ", text)


def contains_all(answer: str, expected: list[str]) -> tuple[bool, float]:
    """Every expected term is present. Score is the fraction found, so near-misses are visible."""
    if not expected:
        return True, 1.0
    normalised = _normalise(answer)
    found = sum(1 for term in expected if _normalise(term) in normalised)
    return found == len(expected), found / len(expected)


def contains_any(answer: str, expected: list[str]) -> tuple[bool, float]:
    """At least one acceptable phrasing appears. For questions with several right answers."""
    if not expected:
        return True, 1.0
    normalised = _normalise(answer)
    hit = any(_normalise(term) in normalised for term in expected)
    return hit, 1.0 if hit else 0.0


def contains_none(answer: str, forbidden: list[str]) -> tuple[bool, float]:
    """No forbidden term appears. This is the hallucination guard.

    Used where the corpus deliberately does *not* contain something: an answer that confidently
    supplies it has invented it.
    """
    if not forbidden:
        return True, 1.0
    normalised = _normalise(answer)
    leaked = [term for term in forbidden if _normalise(term) in normalised]
    return not leaked, 0.0 if leaked else 1.0


def admits_ignorance(answer: str) -> tuple[bool, float]:
    """The answer says it does not know, rather than inventing something.

    Deliberately generous in what it accepts: models phrase a refusal many ways, and the
    behaviour being measured is the honesty, not the wording.
    """
    markers = [
        "not specify", "not specified", "does not specify", "doesn't specify",
        "no information",
        "not mention", "do not mention", "does not mention", "doesn't mention",
        "not mentioned", "not stated", "not provided", "not covered", "cannot find",
        "could not find", "do not have", "don't have", "not in the excerpt",
        "not included", "unable to", "no mention", "not say", "doesn't say",
        "does not say", "not available", "not addressed",
    ]
    normalised = _normalise(answer)
    hit = any(marker in normalised for marker in markers)
    return hit, 1.0 if hit else 0.0


def cites_document(citations: list, expected_filename: str) -> tuple[bool, float]:
    """A citation points at the file that actually holds the answer.

    This is citation *quality*, not merely citation presence — an answer that cites the wrong
    document is worse than one that cites nothing, because it looks verified.
    """
    if not citations:
        return False, 0.0
    filenames = [c.get("filename", "").lower() for c in citations]
    if any(expected_filename.lower() in name for name in filenames):
        # Full marks only when the *top* citation is the right one; half when it is merely in
        # the list, since the reader checks the first source first.
        top = citations[0].get("filename", "").lower()
        return True, 1.0 if expected_filename.lower() in top else 0.5
    return False, 0.0


def has_inline_citation(answer: str) -> tuple[bool, float]:
    """The answer marks which claim came from which excerpt, e.g. ``[2]``."""
    hit = bool(re.search(r"\[\d+\]", answer))
    return hit, 1.0 if hit else 0.0


def recalled_memory(memory_used: list, expected_fragment: str) -> tuple[bool, float]:
    """A specific memory was actually injected into the prompt.

    Checks the *mechanism*, not the prose: whether the platform retrieved the right memory is a
    fact about the system, while whether the model then obeyed it is a fact about the model.
    Both are measured, separately.
    """
    if not memory_used:
        return False, 0.0
    joined = _normalise(" ".join(item.get("content", "") for item in memory_used))
    hit = _normalise(expected_fragment) in joined
    return hit, 1.0 if hit else 0.0


def structured_has_fields(structured: dict | None, required: list[str]) -> tuple[bool, float]:
    """A structured skill returned every field, each non-empty."""
    if not structured:
        return False, 0.0
    present = sum(1 for field_name in required if structured.get(field_name))
    return present == len(required), present / max(len(required), 1)


def within_sentences(answer: str, maximum: int) -> tuple[bool, float]:
    """The answer respects a stated length preference. Used to check memory *changed behaviour*."""
    sentences = [s for s in re.split(r"[.!?]+", answer) if s.strip()]
    ok = len(sentences) <= maximum
    return ok, 1.0 if ok else 0.0


# --------------------------------------------------------------------- aggregate
def summarise(results: list[ScenarioResult]) -> dict:
    """The five metrics the challenge asks for, plus the breakdown behind them."""
    if not results:
        return {}

    passed = [r for r in results if r.passed]
    latencies = sorted(r.latency_ms for r in results if r.latency_ms)

    by_category: dict[str, dict] = {}
    for result in results:
        bucket = by_category.setdefault(
            result.category, {"total": 0, "passed": 0, "score": 0.0}
        )
        bucket["total"] += 1
        bucket["passed"] += int(result.passed)
        bucket["score"] += result.score
    for bucket in by_category.values():
        bucket["accuracy"] = round(bucket["passed"] / bucket["total"], 3)
        bucket["mean_score"] = round(bucket["score"] / bucket["total"], 3)
        del bucket["score"]

    def category_accuracy(name: str) -> float | None:
        bucket = by_category.get(name)
        return bucket["accuracy"] if bucket else None

    citation_scores = [
        r.checks.get("_citation_score", 0.0) for r in results
        if "_citation_score" in r.checks
    ]

    return {
        "scenarios": len(results),
        # --- the five required metrics ---
        "accuracy": round(len(passed) / len(results), 3),
        "mean_response_time_ms": int(sum(latencies) / len(latencies)) if latencies else 0,
        "p95_response_time_ms": latencies[int(len(latencies) * 0.95)] if latencies else 0,
        "memory_recall": category_accuracy("memory"),
        "citation_quality": (
            round(sum(citation_scores) / len(citation_scores), 3) if citation_scores else None
        ),
        "task_success": round(sum(r.score for r in results) / len(results), 3),
        # --- supporting detail ---
        "errors": sum(1 for r in results if r.error),
        "by_category": by_category,
        "failed_scenarios": [r.scenario_id for r in results if not r.passed],
    }
