"""Groundedness quality gate: prove the evaluator classifies known cases correctly.

The mock model provider's output is a generic acknowledgement, not a real
answer, so grading its output against a "must be grounded" bar would be
meaningless. What this gate actually proves is that `GroundednessEvaluator`
itself correctly distinguishes grounded answers from unrelated, uncited and
fabricated-citation ones — the signal that matters once a real model is
configured (ADR-006/012).
"""

import asyncio
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from enterprise_genai_platform.gateway.app import create_app
from enterprise_genai_platform.gateway.config import Settings
from enterprise_genai_platform.rag.groundedness import GroundednessEvaluator
from enterprise_genai_platform.rag.models import Citation, RetrievalHit, RetrievalResult
from enterprise_genai_platform.rag.synthesis import synthesize_grounded_answer

ROOT = Path(__file__).resolve().parents[1]

_EVIDENCE_TEXT = "Refunds above GBP 100 require approval from an operations officer."
_EVIDENCE_CHUNK_ID = "POL-REF-002#chunk-1"


class GroundednessCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    answer: str
    expected_is_grounded: bool


def _evidence() -> RetrievalResult:
    return RetrievalResult(
        hits=(
            RetrievalHit(
                text=_EVIDENCE_TEXT,
                score=0.9,
                citation=Citation(
                    document_id="POL-REF-002",
                    chunk_id=_EVIDENCE_CHUNK_ID,
                    title="Refund Approval",
                    version="1.0",
                    provenance_sha256="a" * 64,
                ),
            ),
        )
    )


def _cases() -> tuple[GroundednessCase, ...]:
    return (
        GroundednessCase(
            case_id="grounded-and-cited",
            answer=(
                f"Refunds above GBP 100 require operations officer approval [{_EVIDENCE_CHUNK_ID}]."
            ),
            expected_is_grounded=True,
        ),
        GroundednessCase(
            case_id="unrelated-to-evidence",
            answer="The weather today is sunny with a light breeze from the coast.",
            expected_is_grounded=False,
        ),
        GroundednessCase(
            case_id="correct-but-uncited",
            answer="Refunds above GBP 100 require approval from an operations officer.",
            expected_is_grounded=False,
        ),
        GroundednessCase(
            case_id="fabricated-citation",
            answer="Refunds above GBP 100 require approval [POL-REF-999#chunk-3].",
            expected_is_grounded=False,
        ),
    )


async def _live_pipeline_sample() -> dict[str, object]:
    """Exercise retrieve -> synthesize -> evaluate through the real app (mock model)."""
    app = create_app(Settings.model_validate({"app_env": "test"}))
    query = "Find the delayed payment policy procedure"
    evidence = await app.state.retriever.retrieve(query, caller_roles=frozenset({"agent.invoke"}))
    answer = await synthesize_grounded_answer(
        app.state.model_gateway,
        model="mock-deterministic",
        query=query,
        evidence=evidence,
        tenant="groundedness-evaluation-script",
    )
    report = app.state.groundedness_evaluator.evaluate(answer, evidence)
    return {
        "query": query,
        "evidence_hit_count": len(evidence.hits),
        "term_overlap_score": report.term_overlap_score,
        "is_grounded": report.is_grounded,
        "note": "mock provider does not cite evidence; low/ungrounded score is expected",
    }


async def main() -> None:
    evaluator = GroundednessEvaluator()
    results = []
    for case in _cases():
        report = evaluator.evaluate(case.answer, _evidence())
        passed = report.is_grounded == case.expected_is_grounded
        results.append(
            {
                "case_id": case.case_id,
                "expected_is_grounded": case.expected_is_grounded,
                "actual_is_grounded": report.is_grounded,
                "term_overlap_score": report.term_overlap_score,
                "fabricated_citations": list(report.fabricated_citations),
                "passed": passed,
            }
        )

    live_sample = await _live_pipeline_sample()
    all_passed = all(result["passed"] for result in results)
    output = {
        "evaluator_cases": results,
        "evaluator_cases_passed": sum(1 for result in results if result["passed"]),
        "evaluator_cases_total": len(results),
        "live_pipeline_sample": live_sample,
        "passed": all_passed,
    }
    report_path = ROOT / ".security-reports/groundedness-evaluation.json"
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))
    if not all_passed:
        raise RuntimeError("groundedness evaluator misclassified one or more known cases")


if __name__ == "__main__":
    asyncio.run(main())
