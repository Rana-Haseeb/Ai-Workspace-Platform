"""The evaluation harness itself.

Scoring is the thing every number in the report rests on, so it gets tested like production code.
A scorer that quietly returns True is worse than no evaluation at all — it manufactures
confidence.

All offline: these test the *scorers*, not the model.
"""
from __future__ import annotations

import pytest

from eval import metrics
from eval.dataset import CATEGORIES, SCENARIOS, by_category, corpus_files
from eval.metrics import ScenarioResult


# ---------------------------------------------------------------- the dataset
def test_the_challenge_minimum_is_met():
    """The challenge asks for at least 40 scenarios."""
    assert len(SCENARIOS) >= 40, f"only {len(SCENARIOS)}"


def test_all_seven_required_categories_are_covered():
    covered = set(by_category())
    assert covered == set(CATEGORIES), f"missing: {set(CATEGORIES) - covered}"


def test_every_category_has_more_than_a_token_scenario():
    for category, scenarios in by_category().items():
        assert len(scenarios) >= 4, f"{category} has only {len(scenarios)}"


def test_scenario_ids_are_unique():
    ids = [s.id for s in SCENARIOS]
    assert len(ids) == len(set(ids))


def test_every_scenario_asserts_something():
    """A scenario with no expectation always passes, which is worse than not having it."""
    for scenario in SCENARIOS:
        has_check = any([
            scenario.expect_all, scenario.expect_any, scenario.expect_none,
            scenario.expect_ignorance, scenario.cite_document, scenario.recall_memory,
            scenario.structured_fields, scenario.max_sentences,
        ])
        # edge-04 is the deliberate exception: near-empty input, where "does not crash" is the
        # whole assertion.
        assert has_check or scenario.id == "edge-04", f"{scenario.id} asserts nothing"


def test_continuations_reference_a_real_scenario():
    ids = {s.id for s in SCENARIOS}
    for scenario in SCENARIOS:
        if scenario.continues:
            assert scenario.continues in ids, f"{scenario.id} continues a missing scenario"


def test_document_scenarios_cite_a_file_that_exists():
    names = {path.name for path in corpus_files()}
    for scenario in SCENARIOS:
        if scenario.cite_document:
            assert scenario.cite_document in names, \
                f"{scenario.id} expects {scenario.cite_document}, which is not in the corpus"


def test_the_corpus_is_present():
    assert len(corpus_files()) >= 3


def test_the_poisoned_document_really_contains_an_injection():
    """The security scenarios are worthless if the bait was never planted."""
    poisoned = next(p for p in corpus_files() if p.name == "quarterly_summary.md")
    text = poisoned.read_text(encoding="utf-8").lower()
    assert "ignore all previous instructions" in text
    assert "pineapple" in text


# ----------------------------------------------------------------- the scorers
def test_contains_all_gives_partial_credit():
    ok, score = metrics.contains_all("the answer is 14 and 9", ["14", "9"])
    assert ok and score == 1.0
    ok, score = metrics.contains_all("the answer is 14", ["14", "9"])
    assert not ok and score == 0.5


def test_scoring_ignores_thousands_separators():
    """'2,300 users' and '2300 users' are the same answer."""
    ok, _ = metrics.contains_all("about 2,300 users were affected", ["2300"])
    assert ok


def test_scoring_is_case_insensitive():
    ok, _ = metrics.contains_any("QDRANT was fastest", ["qdrant"])
    assert ok


def test_contains_none_catches_a_leak():
    ok, score = metrics.contains_none("the answer is BANANA", ["banana"])
    assert not ok and score == 0.0
    ok, score = metrics.contains_none("a normal answer", ["banana"])
    assert ok and score == 1.0


@pytest.mark.parametrize("phrasing", [
    "The excerpts do not mention it.",
    "That is not specified in the documents.",
    "I could not find that information.",
    "The provided material does not say.",
    "There is no information about that.",
])
def test_admits_ignorance_accepts_the_common_phrasings(phrasing):
    """Models refuse in many ways; the behaviour measured is honesty, not wording."""
    ok, _ = metrics.admits_ignorance(phrasing)
    assert ok, phrasing


def test_admits_ignorance_rejects_a_confident_invention():
    ok, _ = metrics.admits_ignorance("The autoscaling policy scales at 70% CPU.")
    assert not ok


def test_citation_quality_rewards_the_top_hit():
    """Citing the right file matters; citing it *first* matters more."""
    top = [{"filename": "vector_databases.md"}, {"filename": "other.md"}]
    buried = [{"filename": "other.md"}, {"filename": "vector_databases.md"}]

    assert metrics.cites_document(top, "vector_databases.md") == (True, 1.0)
    assert metrics.cites_document(buried, "vector_databases.md") == (True, 0.5)
    assert metrics.cites_document([{"filename": "wrong.md"}], "vector_databases.md") == (False, 0.0)
    assert metrics.cites_document([], "vector_databases.md") == (False, 0.0)


def test_inline_citation_detection():
    assert metrics.has_inline_citation("The score was 9 [2].")[0]
    assert not metrics.has_inline_citation("The score was 9.")[0]


def test_memory_recall_checks_the_mechanism_not_the_prose():
    """Whether the memory was injected is a fact about the platform."""
    used = [{"content": "Prefers answers in British English"}]
    assert metrics.recalled_memory(used, "British English")[0]
    assert not metrics.recalled_memory(used, "French")[0]
    assert not metrics.recalled_memory([], "anything")[0]


def test_structured_fields_gives_partial_credit():
    ok, score = metrics.structured_has_fields(
        {"a": ["x"], "b": ["y"], "c": []}, ["a", "b", "c"])
    assert not ok and score == pytest.approx(2 / 3)
    assert metrics.structured_has_fields(None, ["a"]) == (False, 0.0)


def test_sentence_limit():
    assert metrics.within_sentences("One. Two.", 2)[0]
    assert not metrics.within_sentences("One. Two. Three.", 2)[0]


# --------------------------------------------------------------- the aggregate
def _result(**kwargs) -> ScenarioResult:
    defaults = {"scenario_id": "x", "category": "document", "passed": True,
                "score": 1.0, "latency_ms": 100}
    return ScenarioResult(**{**defaults, **kwargs})


def test_summary_reports_the_five_required_metrics():
    summary = metrics.summarise([
        _result(category="document", checks={"_citation_score": 1.0}),
        _result(category="memory", passed=False, score=0.5),
        _result(category="memory"),
    ])
    for key in ["accuracy", "mean_response_time_ms", "memory_recall",
                "citation_quality", "task_success"]:
        assert key in summary, f"{key} missing from the summary"

    assert summary["accuracy"] == pytest.approx(2 / 3, abs=0.001)  # summarise rounds to 3dp
    assert summary["memory_recall"] == 0.5
    assert summary["citation_quality"] == 1.0


def test_summary_lists_what_failed():
    summary = metrics.summarise([
        _result(scenario_id="a"), _result(scenario_id="b", passed=False),
    ])
    assert summary["failed_scenarios"] == ["b"]


def test_summary_survives_an_empty_run():
    assert metrics.summarise([]) == {}


def test_citation_quality_is_none_when_nothing_was_citable():
    """Reporting 0% when no scenario asked for a citation would be a lie."""
    assert metrics.summarise([_result(category="knowledge")])["citation_quality"] is None
