"""End-to-end local operations workflow tests."""

import asyncio

from enterprise_genai_platform.agents import CustomerAgent, PaymentsAgent, PolicyAgent
from enterprise_genai_platform.domain import NovaBankRepository
from enterprise_genai_platform.mcp_boundary import build_local_mcp_gateway
from enterprise_genai_platform.models import DeterministicMockModel
from enterprise_genai_platform.orchestration import OperationsResult, OperationsWorkflow


def workflow() -> OperationsWorkflow:
    gateway = build_local_mcp_gateway(NovaBankRepository())
    return OperationsWorkflow(
        DeterministicMockModel(),
        CustomerAgent(gateway),
        PaymentsAgent(gateway),
        PolicyAgent(gateway),
    )


async def investigate(query: str) -> OperationsResult:
    return await workflow().investigate(
        query,
        subject="test-user",
        roles=frozenset({"agent.invoke"}),
        request_id="test-request",
    )


def test_operations_workflow_routes_to_payments_agent() -> None:
    result = asyncio.run(investigate("Why is CUST-1098 payment transaction TXN-5001 delayed?"))

    assert result.decision.route == "payments"
    assert result.result.agent == "payments"
    assert result.result.evidence[0].source_id == "TXN-5001"
    assert result.steps == 2


def test_operations_workflow_routes_to_customer_agent() -> None:
    result = asyncio.run(investigate("Show customer CUST-1098 account profile"))

    assert result.decision.route == "customer"
    assert result.result.agent == "customer"


def test_operations_workflow_routes_to_policy_agent() -> None:
    result = asyncio.run(investigate("Find the delayed payment policy procedure"))

    assert result.decision.route == "policy"
    assert result.result.agent == "policy"


def test_operations_workflow_does_not_execute_high_risk_action() -> None:
    result = asyncio.run(investigate("Send a refund of £750 for TXN-5001"))

    assert result.decision.route == "human_review"
    assert result.result.agent == "human_review"
    assert result.result.requires_human_approval is True
    assert result.result.evidence == ()
