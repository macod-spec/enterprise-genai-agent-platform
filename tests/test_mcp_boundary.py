"""MCP contracts, authorization, resilience, and audit tests."""

import asyncio
import time
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from enterprise_genai_platform.domain import NovaBankRepository
from enterprise_genai_platform.mcp_boundary import CallerContext, build_local_mcp_gateway
from enterprise_genai_platform.mcp_boundary.contracts import CustomerRecord, CustomerRequest
from enterprise_genai_platform.mcp_boundary.gateway import (
    GovernedMCPGateway,
    MCPAccessDenied,
    MCPInvalidArguments,
    MCPToolFailure,
    MCPToolNotFound,
    ToolRegistration,
)
from enterprise_genai_platform.mcp_boundary.remote_auth import JWTTokenVerifier
from enterprise_genai_platform.mcp_boundary.servers import (
    CustomerTools,
    PaymentTools,
    PolicyTools,
    create_customer_mcp,
    create_payments_mcp,
    create_policy_mcp,
    create_remote_mcp,
)
from enterprise_genai_platform.rag import build_default_retriever


def caller(
    agent: str = "customer",
    roles: frozenset[str] = frozenset({"agent.invoke"}),
) -> CallerContext:
    return CallerContext.model_validate(
        {
            "subject": "test-user",
            "roles": roles,
            "agent": agent,
            "request_id": "request-123",
        }
    )


def test_official_mcp_servers_publish_only_expected_tools() -> None:
    repository = NovaBankRepository()
    customer = asyncio.run(create_customer_mcp(CustomerTools(repository)).list_tools())
    payments = asyncio.run(create_payments_mcp(PaymentTools(repository)).list_tools())
    policy = asyncio.run(create_policy_mcp(PolicyTools(build_default_retriever())).list_tools())

    assert {tool.name for tool in customer} == {
        "customer.get_customer",
        "customer.get_accounts",
    }
    assert {tool.name for tool in payments} == {"payments.get_transaction"}
    assert {tool.name for tool in policy} == {"policy.search"}
    customer_schema = next(
        tool.inputSchema for tool in customer if tool.name == "customer.get_customer"
    )
    assert customer_schema["required"] == ["customer_id"]
    assert customer_schema["properties"]["customer_id"]["type"] == "string"
    assert CustomerRequest.model_json_schema()["additionalProperties"] is False


def test_gateway_allows_registered_tool_and_writes_redacted_audit() -> None:
    gateway = build_local_mcp_gateway(NovaBankRepository())

    output = asyncio.run(
        gateway.invoke(
            "customer.get_customer",
            {"customer_id": "CUST-1098"},
            caller(),
        )
    )

    assert CustomerRecord.model_validate(output).masked_email == "a***@example.test"
    assert gateway.approved_tools == (
        "customer.get_accounts",
        "customer.get_customer",
        "payments.get_transaction",
        "policy.search",
    )
    audit = gateway.audit.records[-1]
    assert audit.outcome == "success"
    assert audit.subject == "test-user"
    assert audit.argument_fingerprint != "CUST-1098"
    assert len(audit.argument_fingerprint) == 64


def test_gateway_denies_cross_agent_tool_use() -> None:
    gateway = build_local_mcp_gateway(NovaBankRepository())

    with pytest.raises(MCPAccessDenied, match="Agent is not permitted"):
        asyncio.run(
            gateway.invoke(
                "payments.get_transaction",
                {"transaction_id": "TXN-5001"},
                caller("customer"),
            )
        )

    assert gateway.audit.records[-1].outcome == "denied"


def test_gateway_denies_missing_role_and_unknown_tool() -> None:
    gateway = build_local_mcp_gateway(NovaBankRepository())

    with pytest.raises(MCPAccessDenied, match="lacks the required"):
        asyncio.run(
            gateway.invoke(
                "customer.get_customer",
                {"customer_id": "CUST-1098"},
                caller(roles=frozenset()),
            )
        )
    with pytest.raises(MCPToolNotFound, match="not approved"):
        asyncio.run(gateway.invoke("system.shell", {"command": "id"}, caller()))

    assert [record.outcome for record in gateway.audit.records] == ["denied", "denied"]


def test_gateway_rejects_extra_or_malformed_arguments() -> None:
    gateway = build_local_mcp_gateway(NovaBankRepository())

    with pytest.raises(MCPInvalidArguments, match="schema validation"):
        asyncio.run(
            gateway.invoke(
                "customer.get_customer",
                {"customer_id": "invalid", "unexpected": True},
                caller(),
            )
        )

    assert gateway.audit.records[-1].outcome == "invalid"


def test_gateway_enforces_per_subject_tool_rate_limit() -> None:
    gateway = GovernedMCPGateway(rate_limit=1)

    async def handler(payload: CustomerRequest, _caller: CallerContext) -> CustomerRecord:
        return CustomerRecord(
            customer_id=payload.customer_id,
            display_name="Synthetic User",
            contact_preference="email",
            masked_email="s***@example.test",
            classification="confidential-synthetic",
        )

    gateway.register(
        ToolRegistration(
            name="customer.test",
            allowed_agents=frozenset({"customer"}),
            required_roles=frozenset({"agent.invoke"}),
            input_model=CustomerRequest,
            output_model=CustomerRecord,
            handler=handler,
        )
    )
    arguments: dict[str, object] = {"customer_id": "CUST-1098"}
    asyncio.run(gateway.invoke("customer.test", arguments, caller()))

    with pytest.raises(MCPAccessDenied, match="rate limit"):
        asyncio.run(gateway.invoke("customer.test", arguments, caller()))

    assert gateway.audit.records[-1].outcome == "denied"


def test_gateway_retries_timeout_then_fails_closed() -> None:
    gateway = GovernedMCPGateway(timeout_seconds=0.001, max_attempts=2)

    async def slow_handler(payload: CustomerRequest, _caller: CallerContext) -> CustomerRecord:
        await asyncio.sleep(0.01)
        return CustomerRecord(
            customer_id=payload.customer_id,
            display_name="Synthetic User",
            contact_preference="email",
            masked_email="s***@example.test",
            classification="confidential-synthetic",
        )

    gateway.register(
        ToolRegistration(
            name="customer.slow",
            allowed_agents=frozenset({"customer"}),
            required_roles=frozenset({"agent.invoke"}),
            input_model=CustomerRequest,
            output_model=CustomerRecord,
            handler=slow_handler,
        )
    )

    with pytest.raises(MCPToolFailure, match="timed out"):
        asyncio.run(gateway.invoke("customer.slow", {"customer_id": "CUST-1098"}, caller()))

    audit = gateway.audit.records[-1]
    assert audit.outcome == "timeout"
    assert audit.attempt_count == 2


def test_gateway_rejects_invalid_configuration_and_duplicate_tools() -> None:
    with pytest.raises(ValueError, match="limits must be positive"):
        GovernedMCPGateway(timeout_seconds=0)

    gateway = GovernedMCPGateway()

    async def handler(payload: CustomerRequest, _caller: CallerContext) -> CustomerRecord:
        raise LookupError(payload.customer_id)

    registration = ToolRegistration(
        name="customer.duplicate",
        allowed_agents=frozenset({"customer"}),
        required_roles=frozenset({"agent.invoke"}),
        input_model=CustomerRequest,
        output_model=CustomerRecord,
        handler=handler,
    )
    gateway.register(registration)
    with pytest.raises(ValueError, match="Duplicate MCP tool"):
        gateway.register(registration)


def _jwt_material(scope: str = "mcp:customer") -> tuple[JWTTokenVerifier, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    now = int(time.time())
    claims = {
        "iss": "https://identity.local.test",
        "aud": "http://127.0.0.1:18100/mcp",
        "sub": "integration-client",
        "client_id": "integration-client",
        "scope": scope,
        "iat": now,
        "exp": now + 60,
        "jti": str(uuid4()),
    }
    token = jwt.encode(claims, private_key, algorithm="RS256")
    verifier = JWTTokenVerifier(
        public_pem.decode(),
        issuer="https://identity.local.test",
        audience="http://127.0.0.1:18100/mcp",
    )
    return verifier, token


def test_remote_mcp_rejects_missing_token_and_wrong_scope() -> None:
    verifier, wrong_scope_token = _jwt_material("mcp:payments")
    remote = create_remote_mcp(
        "customer",
        CustomerTools(NovaBankRepository()),
        verifier,
        issuer_url="https://identity.local.test",
        resource_url="http://127.0.0.1:18100/mcp",
    )
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "security-test", "version": "1"},
        },
    }
    with TestClient(remote.streamable_http_app(), base_url="http://127.0.0.1:18100") as client:
        assert client.post("/mcp", json=request).status_code == 401
        response = client.post(
            "/mcp",
            json=request,
            headers={
                "Authorization": f"Bearer {wrong_scope_token}",
                "Accept": "application/json, text/event-stream",
            },
        )
    assert response.status_code == 403


def test_remote_mcp_accepts_valid_scoped_token() -> None:
    verifier, token = _jwt_material()
    verified = asyncio.run(verifier.verify_token(token))
    assert verified is not None
    assert verified.subject == "integration-client"
    assert verified.scopes == ["mcp:customer"]

    remote = create_remote_mcp(
        "customer",
        CustomerTools(NovaBankRepository()),
        verifier,
        issuer_url="https://identity.local.test",
        resource_url="http://127.0.0.1:18100/mcp",
    )
    with TestClient(remote.streamable_http_app(), base_url="http://127.0.0.1:18100") as client:
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "integration-test", "version": "1"},
                },
            },
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json, text/event-stream",
            },
        )
    assert response.status_code == 200


def test_remote_verifier_fails_closed_for_tampered_token() -> None:
    verifier, token = _jwt_material()
    header, payload, signature = token.split(".")
    signature = f"{'a' if signature[0] != 'a' else 'b'}{signature[1:]}"
    tampered = ".".join((header, payload, signature))
    assert asyncio.run(verifier.verify_token(tampered)) is None
