"""Offline AI quality and security gate tests."""

import asyncio

import pytest

from enterprise_genai_platform.evaluation.runner import (
    EvaluationCase,
    evaluate_cases,
    load_default_cases,
    run_default_evaluation,
)


def test_default_golden_set_passes_release_threshold() -> None:
    report = run_default_evaluation()

    assert report.total == 12
    assert report.score == 1.0
    assert set(report.category_scores) == {"grounding", "routing", "safety", "security"}
    assert all(score == 1.0 for score in report.category_scores.values())
    assert report.failures == ()


def test_evaluator_reports_regression_and_blocks_release() -> None:
    broken = (
        EvaluationCase(
            case_id="broken",
            category="routing",
            query="Find transaction TXN-5001",
            expected_route="policy",
            expected_agent="policy",
        ),
    )

    report = asyncio.run(evaluate_cases(broken))

    assert report.score == 0
    assert report.failures == ("broken",)
    with pytest.raises(RuntimeError, match="below"):
        run_default_evaluation(minimum_score=1.01)


def test_security_cases_are_present_in_golden_set() -> None:
    cases = load_default_cases()

    assert sum(case.human_approval for case in cases) >= 5
    assert sum(case.category == "security" for case in cases) >= 3
