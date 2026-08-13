"""Deterministic model and LangGraph supervisor tests."""

import asyncio

import pytest

from enterprise_genai_platform.models import DeterministicMockModel, RoutingDecision
from enterprise_genai_platform.orchestration.supervisor import SupervisorWorkflow


def test_mock_model_routes_each_approved_domain() -> None:
    model = DeterministicMockModel()

    payment = asyncio.run(model.classify_route("Why did this payment fail?"))
    customer = asyncio.run(model.classify_route("Show the customer contact preference"))
    policy = asyncio.run(model.classify_route("What is the refund eligibility policy?"))

    assert payment.route == "payments"
    assert customer.route == "customer"
    assert policy.route == "policy"


def test_mock_model_escalates_consequential_financial_action() -> None:
    decision = asyncio.run(DeterministicMockModel().classify_route("Send a refund of £750"))

    assert decision.route == "human_review"
    assert decision.requires_human_approval is True
    assert decision.confidence == 1.0


def test_mock_model_escalates_unknown_capability() -> None:
    decision = asyncio.run(DeterministicMockModel().classify_route("Tell me a joke"))

    assert decision.route == "human_review"
    assert decision.requires_human_approval is True
    assert decision.confidence == 0.0


def test_supervisor_executes_bounded_langgraph() -> None:
    workflow = SupervisorWorkflow(DeterministicMockModel(), max_steps=8)

    result = asyncio.run(workflow.route("Find the failed transaction"))

    assert result.decision.route == "payments"
    assert result.steps == 1
    assert result.error_code is None


def test_supervisor_fails_closed_when_model_provider_fails() -> None:
    class FailingModel:
        async def classify_route(self, query: str) -> RoutingDecision:
            del query
            raise RuntimeError("provider unavailable")

    result = asyncio.run(SupervisorWorkflow(FailingModel()).route("Find a transaction"))

    assert result.decision.route == "human_review"
    assert result.decision.requires_human_approval is True
    assert result.error_code == "MODEL_PROVIDER_FAILURE"


def test_supervisor_rejects_invalid_step_limit() -> None:
    with pytest.raises(ValueError, match="max_steps must be at least 1"):
        SupervisorWorkflow(DeterministicMockModel(), max_steps=0)
