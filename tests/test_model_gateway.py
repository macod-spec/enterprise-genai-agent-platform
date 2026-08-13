"""Policy, telemetry and HTTP tests for the owned model gateway (ADR-006)."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from enterprise_genai_platform.gateway.app import create_app
from enterprise_genai_platform.gateway.config import Settings
from enterprise_genai_platform.model_gateway.adapters.azure_openai import AzureOpenAIChatModel
from enterprise_genai_platform.model_gateway.adapters.mock import MockChatModel
from enterprise_genai_platform.model_gateway.contracts import (
    ChatMessage,
    ModelBudgetExceeded,
    ModelGenerationRequest,
    ModelGenerationResult,
    ModelNotAllowed,
    ModelProviderFailure,
    TokenUsage,
)
from enterprise_genai_platform.model_gateway.factory import build_model_gateway
from enterprise_genai_platform.model_gateway.gateway import ModelGateway
from enterprise_genai_platform.model_gateway.policy import ModelAllowlist, TenantBudgetPolicy
from enterprise_genai_platform.model_gateway.pricing import ModelPrice, PricingTable
from enterprise_genai_platform.safety.content_safety import (
    ContentSafetyBlockedError,
    ContentSafetyPolicy,
    MockContentSafetyProvider,
)
from enterprise_genai_platform.safety.pii import PiiBlockedError, PiiPolicy, PresidioPiiDetector

_PII_DETECTOR = PresidioPiiDetector()


def pii_policy(**overrides: object) -> PiiPolicy:
    values: dict[str, object] = {
        "mask_entities": frozenset({"PERSON", "EMAIL_ADDRESS"}),
        "block_entities": frozenset({"CREDIT_CARD"}),
    }
    values.update(overrides)
    return PiiPolicy(**values)  # type: ignore[arg-type]


def content_safety_policy(**overrides: object) -> ContentSafetyPolicy:
    thresholds: dict[str, int] = {"Hate": 4, "SelfHarm": 4, "Sexual": 4, "Violence": 4}
    thresholds.update(overrides)  # type: ignore[arg-type]
    return ContentSafetyPolicy(thresholds)


def request(**overrides: object) -> ModelGenerationRequest:
    values: dict[str, object] = {
        "model": "mock-deterministic",
        "messages": (ChatMessage(role="user", content="Why did this payment fail?"),),
        "tenant": "tenant-a",
        "agent": "payments",
    }
    values.update(overrides)
    return ModelGenerationRequest.model_validate(values)


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


def test_mock_adapter_returns_zero_cost_deterministic_completion() -> None:
    result = asyncio.run(MockChatModel().generate(request()))

    assert result.provider == "mock"
    assert result.model == "mock-deterministic"
    assert result.usage.total_tokens > 0
    assert result.finish_reason == "stop"


def test_allowlist_denies_unapproved_model() -> None:
    gateway = build_gateway()

    with pytest.raises(ModelNotAllowed, match="not on the governed allowlist"):
        asyncio.run(gateway.generate(request(model="gpt-4o")))


def test_allowlist_rejects_empty_configuration() -> None:
    with pytest.raises(ValueError, match="At least one model"):
        ModelAllowlist(frozenset())


def test_budget_policy_fails_closed_once_ceiling_reached() -> None:
    policy = TenantBudgetPolicy(default_ceiling_gbp=0.001)
    policy.check_and_reserve("tenant-a", 0.0009)

    with pytest.raises(ModelBudgetExceeded, match="would exceed"):
        policy.check_and_reserve("tenant-a", 0.0009)

    assert policy.spent_gbp("tenant-a") == pytest.approx(0.0009)


def test_budget_policy_is_isolated_per_tenant() -> None:
    policy = TenantBudgetPolicy(default_ceiling_gbp=0.001)
    policy.check_and_reserve("tenant-a", 0.0009)

    policy.check_and_reserve("tenant-b", 0.0009)  # does not raise; separate ledger

    assert policy.spent_gbp("tenant-b") == pytest.approx(0.0009)


def test_pricing_table_prices_mock_model_at_zero() -> None:
    table = PricingTable()

    cost = table.estimate_cost_gbp(
        "mock-deterministic", TokenUsage(prompt_tokens=1_000, completion_tokens=1_000)
    )

    assert cost == 0.0


def test_pricing_table_never_reports_zero_for_unpriced_models() -> None:
    table = PricingTable({})

    cost = table.estimate_cost_gbp(
        "unknown-model", TokenUsage(prompt_tokens=1_000, completion_tokens=0)
    )

    assert cost > 0.0


def test_gateway_returns_priced_result() -> None:
    gateway = build_gateway(pricing=PricingTable({"mock-deterministic": ModelPrice(0.01, 0.02)}))

    result = asyncio.run(gateway.generate(request()))

    assert isinstance(result, ModelGenerationResult)
    assert result.provider == "mock"
    assert result.estimated_cost_gbp > 0.0


def test_gateway_fails_closed_after_exhausting_retries() -> None:
    class FailingProvider:
        async def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
            del request
            raise ModelProviderFailure("provider unavailable")

    gateway = build_gateway(provider=FailingProvider(), max_attempts=2)

    with pytest.raises(ModelProviderFailure):
        asyncio.run(gateway.generate(request()))


def test_gateway_rejects_non_positive_limits() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        build_gateway(timeout_seconds=0)


def test_gateway_exposes_allowed_models() -> None:
    gateway = build_gateway()

    assert gateway.allowed_models == frozenset({"mock-deterministic"})


def test_gateway_denies_when_preflight_budget_would_be_exceeded() -> None:
    gateway = build_gateway(
        budget=TenantBudgetPolicy(default_ceiling_gbp=0.0000001),
        pricing=PricingTable({"mock-deterministic": ModelPrice(1.0, 1.0)}),
    )

    with pytest.raises(ModelBudgetExceeded):
        asyncio.run(gateway.generate(request()))


def test_gateway_fails_closed_when_provider_always_times_out() -> None:
    class SlowProvider:
        async def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
            del request
            await asyncio.sleep(1)
            raise AssertionError("unreachable")

    gateway = build_gateway(provider=SlowProvider(), timeout_seconds=0.01, max_attempts=1)

    with pytest.raises(ModelProviderFailure, match="timed out"):
        asyncio.run(gateway.generate(request()))


def test_gateway_masks_pii_in_outgoing_request_before_reaching_provider() -> None:
    class CapturingProvider:
        seen_content: str | None = None

        async def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
            CapturingProvider.seen_content = request.messages[0].content
            return await MockChatModel().generate(request)

    gateway = build_gateway(
        provider=CapturingProvider(), pii_detector=_PII_DETECTOR, pii_policy=pii_policy()
    )

    asyncio.run(
        gateway.generate(
            request(
                messages=(
                    ChatMessage(role="user", content="Contact jane.doe@example.com about this"),
                )
            )
        )
    )

    assert CapturingProvider.seen_content is not None
    assert "jane.doe@example.com" not in CapturingProvider.seen_content
    assert "<EMAIL_ADDRESS>" in CapturingProvider.seen_content


def test_gateway_masks_pii_in_provider_response() -> None:
    class EchoingProvider:
        async def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
            result = await MockChatModel().generate(request)
            return result.model_copy(update={"content": "Reach me at jane.doe@example.com"})

    gateway = build_gateway(
        provider=EchoingProvider(), pii_detector=_PII_DETECTOR, pii_policy=pii_policy()
    )

    result = asyncio.run(gateway.generate(request()))

    assert "jane.doe@example.com" not in result.content
    assert "<EMAIL_ADDRESS>" in result.content


def test_gateway_blocks_request_containing_disallowed_pii() -> None:
    gateway = build_gateway(pii_detector=_PII_DETECTOR, pii_policy=pii_policy())

    with pytest.raises(PiiBlockedError):
        asyncio.run(
            gateway.generate(
                request(
                    messages=(
                        ChatMessage(role="user", content="Card is 4111 1111 1111 1111, charge it"),
                    )
                )
            )
        )


def test_gateway_skips_pii_guard_when_not_configured() -> None:
    gateway = build_gateway()

    result = asyncio.run(
        gateway.generate(
            request(
                messages=(
                    ChatMessage(role="user", content="Contact jane.doe@example.com about this"),
                )
            )
        )
    )

    assert isinstance(result, ModelGenerationResult)


def test_gateway_blocks_request_that_fails_content_safety_policy() -> None:
    gateway = build_gateway(
        content_safety_provider=MockContentSafetyProvider(),
        content_safety_policy=content_safety_policy(),
    )

    with pytest.raises(ContentSafetyBlockedError):
        asyncio.run(
            gateway.generate(request(messages=(ChatMessage(role="user", content="bomb threat"),)))
        )


def test_gateway_allows_benign_request_through_content_safety_policy() -> None:
    gateway = build_gateway(
        content_safety_provider=MockContentSafetyProvider(),
        content_safety_policy=content_safety_policy(),
    )

    result = asyncio.run(gateway.generate(request()))

    assert isinstance(result, ModelGenerationResult)


def test_gateway_blocks_response_that_fails_content_safety_policy() -> None:
    class UnsafeEchoingProvider:
        async def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
            result = await MockChatModel().generate(request)
            return result.model_copy(update={"content": "this is a bomb threat"})

    gateway = build_gateway(
        provider=UnsafeEchoingProvider(),
        content_safety_provider=MockContentSafetyProvider(),
        content_safety_policy=content_safety_policy(),
    )

    with pytest.raises(ContentSafetyBlockedError):
        asyncio.run(gateway.generate(request()))


def test_gateway_fails_closed_when_content_safety_provider_errors() -> None:
    class FailingContentSafetyProvider:
        async def check(self, text: str) -> tuple:  # type: ignore[type-arg]
            del text
            raise RuntimeError("content safety endpoint unreachable")

    gateway = build_gateway(
        content_safety_provider=FailingContentSafetyProvider(),
        content_safety_policy=content_safety_policy(),
    )

    with pytest.raises(ContentSafetyBlockedError, match="unavailable"):
        asyncio.run(gateway.generate(request()))


def test_gateway_skips_content_safety_guard_when_not_configured() -> None:
    gateway = build_gateway()

    result = asyncio.run(
        gateway.generate(request(messages=(ChatMessage(role="user", content="bomb threat"),)))
    )

    assert isinstance(result, ModelGenerationResult)


def test_factory_builds_mock_gateway_by_default() -> None:
    gateway = build_model_gateway(Settings.model_validate({"app_env": "test"}))

    assert gateway.allowed_models == frozenset({"mock-deterministic"})


def test_factory_builds_azure_openai_adapter_without_network_calls() -> None:
    gateway = build_model_gateway(
        Settings.model_validate(
            {
                "app_env": "test",
                "model_gateway_provider": "azure_openai",
                "model_gateway_allowlist": ["gpt-4o-mini"],
                "azure_openai_endpoint": "https://example-oai.openai.azure.com",
            }
        )
    )

    assert gateway.allowed_models == frozenset({"gpt-4o-mini"})


def test_azure_openai_adapter_rejects_missing_configuration() -> None:
    with pytest.raises(ValueError, match="endpoint and api_version are required"):
        AzureOpenAIChatModel(endpoint="", api_version="2024-10-21", timeout_seconds=5.0)


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "test",
        "cors_allowed_origins": ["http://localhost:3000"],
        "rate_limit_requests": 10,
    }
    values.update(overrides)
    return Settings.model_validate(values)


def test_model_gateway_http_route_requires_role() -> None:
    client = TestClient(create_app(settings()))

    response = client.post(
        "/api/v1/model-gateway/generate",
        json={"model": "mock-deterministic", "messages": [{"role": "user", "content": "hi"}]},
        headers={"X-Local-User": "developer", "X-Local-Roles": "platform.viewer"},
    )

    assert response.status_code == 403


def test_model_gateway_http_route_generates_and_returns_usage() -> None:
    client = TestClient(create_app(settings()))

    response = client.post(
        "/api/v1/model-gateway/generate",
        json={
            "model": "mock-deterministic",
            "messages": [{"role": "user", "content": "Why did this payment fail?"}],
        },
        headers={
            "X-Local-User": "developer",
            "X-Local-Roles": "agent.invoke",
            "X-Local-Tenant": "payment-disputes",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "mock"
    assert body["estimated_cost_gbp"] == 0.0
    assert body["usage"]["prompt_tokens"] > 0


def test_model_gateway_http_route_emits_gateway_metrics() -> None:
    client = TestClient(create_app(settings()))

    client.post(
        "/api/v1/model-gateway/generate",
        json={
            "model": "mock-deterministic",
            "messages": [{"role": "user", "content": "hi"}],
        },
        headers={"X-Local-User": "developer", "X-Local-Roles": "agent.invoke"},
    )
    metrics = client.get("/metrics").text

    assert "agent_platform_model_gateway_calls_total" in metrics
    assert "agent_platform_model_gateway_duration_seconds" in metrics


def test_model_gateway_http_route_denies_unapproved_model() -> None:
    client = TestClient(create_app(settings()))

    response = client.post(
        "/api/v1/model-gateway/generate",
        json={
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "hi"}],
        },
        headers={
            "X-Local-User": "developer",
            "X-Local-Roles": "agent.invoke",
            "X-Local-Tenant": "payment-disputes",
        },
    )

    assert response.status_code == 403


def test_model_gateway_http_route_masks_pii_by_default() -> None:
    client = TestClient(create_app(settings()))

    response = client.post(
        "/api/v1/model-gateway/generate",
        json={
            "model": "mock-deterministic",
            "messages": [{"role": "user", "content": "Contact jane.doe@example.com please"}],
        },
        headers={
            "X-Local-User": "developer",
            "X-Local-Roles": "agent.invoke",
            "X-Local-Tenant": "payment-disputes",
        },
    )

    assert response.status_code == 200
    assert "jane.doe@example.com" not in response.text


def test_model_gateway_http_route_blocks_disallowed_pii_by_default() -> None:
    client = TestClient(create_app(settings()))

    response = client.post(
        "/api/v1/model-gateway/generate",
        json={
            "model": "mock-deterministic",
            "messages": [{"role": "user", "content": "Card is 4111 1111 1111 1111, charge it"}],
        },
        headers={
            "X-Local-User": "developer",
            "X-Local-Roles": "agent.invoke",
            "X-Local-Tenant": "payment-disputes",
        },
    )

    assert response.status_code == 400
    assert "CREDIT_CARD" in response.json()["detail"]
    assert "4111 1111 1111 1111" not in response.text


def test_model_gateway_http_route_pii_protection_can_be_disabled() -> None:
    client = TestClient(create_app(settings(pii_protection_enabled=False)))

    response = client.post(
        "/api/v1/model-gateway/generate",
        json={
            "model": "mock-deterministic",
            "messages": [{"role": "user", "content": "Card is 4111 1111 1111 1111, charge it"}],
        },
        headers={
            "X-Local-User": "developer",
            "X-Local-Roles": "agent.invoke",
            "X-Local-Tenant": "payment-disputes",
        },
    )

    assert response.status_code == 200


def test_model_gateway_http_route_blocks_unsafe_content_by_default() -> None:
    client = TestClient(create_app(settings()))

    response = client.post(
        "/api/v1/model-gateway/generate",
        json={
            "model": "mock-deterministic",
            "messages": [{"role": "user", "content": "this is a bomb threat"}],
        },
        headers={
            "X-Local-User": "developer",
            "X-Local-Roles": "agent.invoke",
            "X-Local-Tenant": "payment-disputes",
        },
    )

    assert response.status_code == 400
    assert "Violence" in response.json()["detail"]


def test_model_gateway_http_route_content_safety_can_be_disabled() -> None:
    client = TestClient(create_app(settings(content_safety_enabled=False)))

    response = client.post(
        "/api/v1/model-gateway/generate",
        json={
            "model": "mock-deterministic",
            "messages": [{"role": "user", "content": "this is a bomb threat"}],
        },
        headers={
            "X-Local-User": "developer",
            "X-Local-Roles": "agent.invoke",
            "X-Local-Tenant": "payment-disputes",
        },
    )

    assert response.status_code == 200
