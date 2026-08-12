"""Deterministic golden-set evaluator for routing, tools, citations, and safety."""

import asyncio
import json
from importlib.resources import files
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from enterprise_genai_platform.agents import CustomerAgent, PaymentsAgent, PolicyAgent
from enterprise_genai_platform.domain import NovaBankRepository
from enterprise_genai_platform.mcp_boundary import build_local_mcp_gateway
from enterprise_genai_platform.models import DeterministicMockModel
from enterprise_genai_platform.orchestration import OperationsWorkflow

ROOT = Path(__file__).resolve().parents[3]


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    category: str
    query: str
    expected_route: str
    expected_agent: str
    expected_source: str | None = None
    expected_error_code: str | None = None
    human_approval: bool = False


class EvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    total: int
    passed: int
    score: float = Field(ge=0, le=1)
    category_scores: dict[str, float]
    failures: tuple[str, ...]


async def evaluate_cases(cases: tuple[EvaluationCase, ...]) -> EvaluationReport:
    repository = NovaBankRepository()
    gateway = build_local_mcp_gateway(repository)
    workflow = OperationsWorkflow(
        DeterministicMockModel(),
        CustomerAgent(gateway),
        PaymentsAgent(gateway),
        PolicyAgent(gateway),
    )
    failures: list[str] = []
    category_totals: dict[str, int] = {}
    category_passed: dict[str, int] = {}
    for case in cases:
        result = await workflow.investigate(
            case.query,
            subject="evaluation-runner",
            roles=frozenset({"agent.invoke", "privacy.read"}),
            request_id=case.case_id,
        )
        source_ids = {evidence.source_id for evidence in result.result.evidence}
        checks = (
            result.decision.route == case.expected_route,
            result.result.agent == case.expected_agent,
            result.result.requires_human_approval is case.human_approval,
            case.expected_source is None or case.expected_source in source_ids,
            result.result.error_code == case.expected_error_code,
        )
        case_passed = all(checks)
        category_totals[case.category] = category_totals.get(case.category, 0) + 1
        if case_passed:
            category_passed[case.category] = category_passed.get(case.category, 0) + 1
        else:
            failures.append(case.case_id)
    passed = len(cases) - len(failures)
    return EvaluationReport(
        total=len(cases),
        passed=passed,
        score=passed / len(cases) if cases else 0,
        category_scores={
            category: category_passed.get(category, 0) / total
            for category, total in sorted(category_totals.items())
        },
        failures=tuple(failures),
    )


def load_default_cases() -> tuple[EvaluationCase, ...]:
    resource = files("enterprise_genai_platform.evaluation").joinpath("golden_cases.json")
    payload = json.loads(resource.read_text(encoding="utf-8"))
    return tuple(EvaluationCase.model_validate(item) for item in payload)


def run_default_evaluation(*, minimum_score: float = 1.0) -> EvaluationReport:
    report = asyncio.run(evaluate_cases(load_default_cases()))
    if report.score < minimum_score:
        raise RuntimeError(f"Evaluation score {report.score:.3f} is below {minimum_score:.3f}")
    failing_categories = [
        category for category, score in report.category_scores.items() if score < minimum_score
    ]
    if failing_categories:
        raise RuntimeError(
            "Evaluation categories below threshold: " + ", ".join(failing_categories)
        )
    return report


def main() -> None:
    report = run_default_evaluation()
    report_path = ROOT / ".security-reports/evaluation.json"
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
