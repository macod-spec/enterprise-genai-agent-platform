"""Grounded-answer synthesis and the /rag/answer HTTP endpoint (ADR-012)."""

import asyncio

from fastapi.testclient import TestClient

from enterprise_genai_platform.gateway.app import create_app
from enterprise_genai_platform.gateway.config import Settings
from enterprise_genai_platform.model_gateway.adapters.mock import MockChatModel
from enterprise_genai_platform.model_gateway.contracts import (
    ModelGenerationRequest,
    ModelGenerationResult,
)
from enterprise_genai_platform.model_gateway.gateway import ModelGateway
from enterprise_genai_platform.model_gateway.policy import ModelAllowlist, TenantBudgetPolicy
from enterprise_genai_platform.model_gateway.pricing import PricingTable
from enterprise_genai_platform.rag.models import Citation, RetrievalHit, RetrievalResult
from enterprise_genai_platform.rag.synthesis import (
    build_synthesis_prompt,
    synthesize_grounded_answer,
)


def evidence() -> RetrievalResult:
    return RetrievalResult(
        hits=(
            RetrievalHit(
                text="Refunds above GBP 100 require approval from an operations officer.",
                score=0.9,
                citation=Citation(
                    document_id="POL-REF-002",
                    chunk_id="POL-REF-002#chunk-1",
                    title="Refund Approval",
                    version="1.0",
                    provenance_sha256="a" * 64,
                ),
            ),
        )
    )


def build_gateway(**overrides: object) -> ModelGateway:
    values: dict[str, object] = {
        "provider": MockChatModel(),
        "provider_name": "mock",
        "allowlist": ModelAllowlist(frozenset({"mock-deterministic"})),
        "budget": TenantBudgetPolicy(default_ceiling_gbp=5.0),
        "pricing": PricingTable(),
    }
    values.update(overrides)
    provider = values.pop("provider")
    return ModelGateway(provider, **values)  # type: ignore[arg-type]


def test_synthesis_prompt_embeds_only_retrieved_evidence_and_the_question() -> None:
    prompt = build_synthesis_prompt("Are refunds always allowed?", evidence())

    assert "Are refunds always allowed?" in prompt
    assert "[POL-REF-002#chunk-1]" in prompt
    assert "operations officer" in prompt


def test_synthesize_refuses_when_no_evidence_was_retrieved() -> None:
    gateway = build_gateway()

    answer = asyncio.run(
        synthesize_grounded_answer(
            gateway,
            model="mock-deterministic",
            query="Anything at all?",
            evidence=RetrievalResult(hits=()),
            tenant="tenant-a",
        )
    )

    assert "no relevant evidence" in answer.lower()


def test_synthesize_calls_the_model_gateway_with_the_evidence_grounded_prompt() -> None:
    class CapturingProvider:
        seen_prompt: str | None = None

        async def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
            CapturingProvider.seen_prompt = request.messages[0].content
            return await MockChatModel().generate(request)

    gateway = build_gateway(provider=CapturingProvider())

    asyncio.run(
        synthesize_grounded_answer(
            gateway,
            model="mock-deterministic",
            query="What is the refund approval threshold?",
            evidence=evidence(),
            tenant="tenant-a",
        )
    )

    assert CapturingProvider.seen_prompt is not None
    assert "POL-REF-002#chunk-1" in CapturingProvider.seen_prompt
    assert "refund approval threshold" in CapturingProvider.seen_prompt.lower()


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "test",
        "cors_allowed_origins": ["http://localhost:3000"],
        "rate_limit_requests": 10,
    }
    values.update(overrides)
    return Settings.model_validate(values)


def test_rag_answer_endpoint_requires_role() -> None:
    client = TestClient(create_app(settings()))

    response = client.post(
        "/api/v1/rag/answer",
        json={"query": "What is the refund approval threshold?"},
        headers={"X-Local-User": "developer", "X-Local-Roles": "platform.viewer"},
    )

    assert response.status_code == 403


def test_rag_answer_endpoint_returns_citations_and_groundedness_signals() -> None:
    client = TestClient(create_app(settings()))

    response = client.post(
        "/api/v1/rag/answer",
        json={"query": "Find the delayed payment policy procedure"},
        headers={
            "X-Local-User": "developer",
            "X-Local-Roles": "agent.invoke",
            "X-Local-Tenant": "payment-disputes",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["citations"]
    assert body["citations"][0]["document_id"] == "POL-PAY-001"
    assert isinstance(body["term_overlap_score"], float)
    assert isinstance(body["is_grounded"], bool)
    # The mock provider echoes a generic acknowledgement rather than citing
    # evidence, so this is honestly ungrounded rather than faked as passing.
    assert body["is_grounded"] is False


def test_rag_answer_endpoint_rejects_overlong_query() -> None:
    client = TestClient(create_app(settings()))

    response = client.post(
        "/api/v1/rag/answer",
        json={"query": "x" * 501},
        headers={
            "X-Local-User": "developer",
            "X-Local-Roles": "agent.invoke",
            "X-Local-Tenant": "payment-disputes",
        },
    )

    assert response.status_code == 422


def test_rag_answer_endpoint_emits_model_gateway_metrics() -> None:
    client = TestClient(create_app(settings()))

    client.post(
        "/api/v1/rag/answer",
        json={"query": "Find the delayed payment policy procedure"},
        headers={
            "X-Local-User": "developer",
            "X-Local-Roles": "agent.invoke",
            "X-Local-Tenant": "payment-disputes",
        },
    )
    metrics = client.get("/metrics").text

    assert "agent_platform_model_gateway_calls_total" in metrics
    assert "agent_platform_rag_retrievals_total" in metrics
