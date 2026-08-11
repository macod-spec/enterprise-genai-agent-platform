"""Synthetic NovaBank repository and MCP-backed specialist-agent tests."""

import asyncio
from typing import Literal

from enterprise_genai_platform.agents import CustomerAgent, PaymentsAgent, PolicyAgent
from enterprise_genai_platform.domain import NovaBankRepository
from enterprise_genai_platform.mcp_boundary import CallerContext, build_local_mcp_gateway

AgentIdentity = Literal["customer", "payments", "policy"]


def caller(agent: AgentIdentity) -> CallerContext:
    return CallerContext(
        subject="test-user",
        roles=frozenset({"agent.invoke"}),
        agent=agent,
        request_id="test-request",
    )


def test_repository_contains_only_expected_synthetic_records() -> None:
    repository = NovaBankRepository()
    customer = repository.get_customer("CUST-1098")
    transaction = repository.get_transaction("TXN-5001")

    assert customer is not None
    assert customer.classification == "confidential-synthetic"
    assert customer.masked_email.endswith("@example.test")
    assert transaction is not None
    assert transaction.customer_id == "CUST-1098"
    assert repository.get_customer("CUST-9999") is None


def test_customer_agent_returns_masked_minimum_data() -> None:
    agent = CustomerAgent(build_local_mcp_gateway(NovaBankRepository()))
    result = asyncio.run(agent.investigate("Show customer CUST-1098 accounts", caller("customer")))

    assert result.agent == "customer"
    assert result.error_code is None
    assert len(result.evidence) == 3
    assert "a***@example.test" in result.evidence[0].detail


def test_customer_agent_requires_valid_identifier() -> None:
    agent = CustomerAgent(build_local_mcp_gateway(NovaBankRepository()))

    missing = asyncio.run(agent.investigate("Show this customer", caller("customer")))
    unknown = asyncio.run(agent.investigate("Show CUST-9999", caller("customer")))

    assert missing.error_code == "CUSTOMER_ID_REQUIRED"
    assert unknown.error_code == "CUSTOMER_TOOL_FAILURE"


def test_payments_agent_returns_read_only_evidence() -> None:
    agent = PaymentsAgent(build_local_mcp_gateway(NovaBankRepository()))
    result = asyncio.run(
        agent.investigate(
            "Why is CUST-1098 transaction TXN-5001 delayed?",
            caller("payments"),
        )
    )

    assert result.agent == "payments"
    assert result.error_code is None
    assert "no payment action was executed" in result.summary
    assert "2500.00" in result.evidence[0].detail


def test_payments_agent_blocks_mismatched_customer_relationship() -> None:
    agent = PaymentsAgent(build_local_mcp_gateway(NovaBankRepository()))
    result = asyncio.run(
        agent.investigate("Show CUST-2042 transaction TXN-5001", caller("payments"))
    )

    assert result.error_code == "CUSTOMER_TRANSACTION_MISMATCH"
    assert result.requires_human_approval is True
    assert result.evidence == ()


def test_payments_agent_handles_missing_and_unknown_identifiers() -> None:
    agent = PaymentsAgent(build_local_mcp_gateway(NovaBankRepository()))

    missing = asyncio.run(agent.investigate("Find my payment", caller("payments")))
    unknown = asyncio.run(agent.investigate("Find TXN-9999", caller("payments")))

    assert missing.error_code == "TRANSACTION_ID_REQUIRED"
    assert unknown.error_code == "PAYMENT_TOOL_FAILURE"


def test_policy_agent_returns_citable_policy_evidence() -> None:
    agent = PolicyAgent(build_local_mcp_gateway(NovaBankRepository()))
    result = asyncio.run(agent.investigate("What is the delayed payment policy?", caller("policy")))

    assert result.agent == "policy"
    assert result.error_code is None
    assert result.evidence[0].source_id == "POL-PAY-001"
    assert result.evidence[0].source_type == "policy"


def test_policy_agent_escalates_when_no_policy_matches() -> None:
    agent = PolicyAgent(build_local_mcp_gateway(NovaBankRepository()))
    result = asyncio.run(agent.investigate("astronomy weather", caller("policy")))

    assert result.error_code == "POLICY_NOT_FOUND"
    assert result.requires_human_approval is True
