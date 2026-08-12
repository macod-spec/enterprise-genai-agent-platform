"""Deterministic groundedness scoring tests (ADR-012)."""

import pytest

from enterprise_genai_platform.rag.groundedness import GroundednessEvaluator
from enterprise_genai_platform.rag.models import Citation, RetrievalHit, RetrievalResult


def evidence(*, chunk_id: str = "POL-PAY-001#chunk-1", text: str) -> RetrievalResult:
    return RetrievalResult(
        hits=(
            RetrievalHit(
                text=text,
                score=0.9,
                citation=Citation(
                    document_id="POL-PAY-001",
                    chunk_id=chunk_id,
                    title="Delayed Faster Payments",
                    version="1.0",
                    provenance_sha256="a" * 64,
                ),
            ),
        )
    )


def test_well_grounded_answer_scores_high_and_cites_real_evidence() -> None:
    hits = evidence(
        text=(
            "When a Faster Payment is delayed, confirm the transaction status "
            "and beneficiary details before escalation to payment operations."
        )
    )
    answer = (
        "Confirm the transaction status and beneficiary details before "
        "escalation to payment operations [POL-PAY-001#chunk-1]."
    )

    report = GroundednessEvaluator().evaluate(answer, hits)

    assert report.term_overlap_score > 0.8
    assert report.citations_found == ("POL-PAY-001#chunk-1",)
    assert report.fabricated_citations == ()
    assert report.is_grounded is True


def test_unrelated_answer_scores_low_and_is_not_grounded() -> None:
    hits = evidence(text="Refunds above GBP 100 require approval from an operations officer.")
    answer = "The weather today is sunny with a light breeze from the coast."

    report = GroundednessEvaluator().evaluate(answer, hits)

    assert report.term_overlap_score < 0.3
    assert report.is_grounded is False


def test_fabricated_citation_is_flagged_and_never_grounded() -> None:
    hits = evidence(text="Refunds above GBP 100 require approval from an operations officer.")
    answer = "Refunds above GBP 100 require approval [POL-REF-999#chunk-3]."

    report = GroundednessEvaluator().evaluate(answer, hits)

    assert report.fabricated_citations == ("POL-REF-999#chunk-3",)
    assert report.is_grounded is False


def test_answer_without_any_citation_is_not_grounded_even_with_high_overlap() -> None:
    hits = evidence(text="Refunds above GBP 100 require approval from an operations officer.")
    answer = "Refunds above GBP 100 require approval from an operations officer."

    report = GroundednessEvaluator().evaluate(answer, hits)

    assert report.term_overlap_score > 0.8
    assert report.citations_found == ()
    assert report.is_grounded is False


def test_empty_answer_scores_zero_without_dividing_by_zero() -> None:
    hits = evidence(text="Refunds above GBP 100 require approval from an operations officer.")

    report = GroundednessEvaluator().evaluate("", hits)

    assert report.term_overlap_score == 0.0
    assert report.is_grounded is False


def test_no_evidence_at_all_yields_zero_overlap() -> None:
    empty_evidence = RetrievalResult(hits=())

    report = GroundednessEvaluator().evaluate(
        "Refunds require approval [POL-REF-001#chunk-1].", empty_evidence
    )

    assert report.term_overlap_score == 0.0
    assert report.fabricated_citations == ("POL-REF-001#chunk-1",)
    assert report.is_grounded is False


def test_threshold_is_configurable() -> None:
    hits = evidence(text="Refunds above GBP 100 require approval from an operations officer.")
    answer = "Refunds require approval, though timing can vary by season [POL-PAY-001#chunk-1]."

    lenient = GroundednessEvaluator(minimum_term_overlap=0.1)
    strict = GroundednessEvaluator(minimum_term_overlap=0.99)

    assert lenient.evaluate(answer, hits).is_grounded is True
    assert strict.evaluate(answer, hits).is_grounded is False


def test_evaluator_rejects_invalid_threshold() -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        GroundednessEvaluator(minimum_term_overlap=1.5)
