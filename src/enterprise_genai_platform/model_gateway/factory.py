"""Build a governed ModelGateway from typed application settings."""

from functools import lru_cache

from enterprise_genai_platform.gateway.config import Settings
from enterprise_genai_platform.model_gateway.adapters.azure_openai import AzureOpenAIChatModel
from enterprise_genai_platform.model_gateway.adapters.mock import (
    PROVIDER_NAME as MOCK_PROVIDER_NAME,
)
from enterprise_genai_platform.model_gateway.adapters.mock import MockChatModel
from enterprise_genai_platform.model_gateway.contracts import ChatModelProvider
from enterprise_genai_platform.model_gateway.gateway import ModelGateway
from enterprise_genai_platform.model_gateway.policy import ModelAllowlist, TenantBudgetPolicy
from enterprise_genai_platform.model_gateway.pricing import PricingTable
from enterprise_genai_platform.safety.azure_content_safety import AzureContentSafetyProvider
from enterprise_genai_platform.safety.content_safety import (
    ContentSafetyPolicy,
    ContentSafetyProvider,
    MockContentSafetyProvider,
)
from enterprise_genai_platform.safety.pii import PiiPolicy, PresidioPiiDetector
from enterprise_genai_platform.tenancy.registry import TenantRegistry


@lru_cache
def _shared_pii_detector() -> PresidioPiiDetector:
    """Load the spaCy pipeline once per process; the detector itself is stateless."""
    return PresidioPiiDetector()


def build_model_gateway(
    settings: Settings, *, tenant_registry: TenantRegistry | None = None
) -> ModelGateway:
    """Select the configured provider adapter and wrap it with policy and telemetry.

    When a tenant_registry is supplied, each tenant's own token_budget_gbp
    becomes its ceiling — never a single number shared across tenants.
    settings.model_gateway_daily_budget_gbp remains only as the fallback for
    callers with no tenant bundle at all (mock/local-dev paths without
    tenancy wired up).
    """
    provider: ChatModelProvider
    provider_name: str
    if settings.model_gateway_provider == "azure_openai":
        if not settings.azure_openai_endpoint:
            raise ValueError("Azure OpenAI endpoint is required for the azure_openai provider")
        provider = AzureOpenAIChatModel(
            endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
            timeout_seconds=settings.model_gateway_timeout_seconds,
        )
        provider_name = "azure_openai"
    else:
        provider = MockChatModel()
        provider_name = MOCK_PROVIDER_NAME

    pii_detector: PresidioPiiDetector | None = None
    pii_policy: PiiPolicy | None = None
    if settings.pii_protection_enabled:
        pii_detector = _shared_pii_detector()
        pii_policy = PiiPolicy(
            mask_entities=frozenset(settings.pii_mask_entities),
            block_entities=frozenset(settings.pii_block_entities),
            score_threshold=settings.pii_score_threshold,
        )

    content_safety_provider: ContentSafetyProvider | None = None
    content_safety_policy: ContentSafetyPolicy | None = None
    if settings.content_safety_enabled:
        if settings.content_safety_provider == "azure":
            if not settings.content_safety_endpoint:
                raise ValueError("Azure Content Safety endpoint is required")
            content_safety_provider = AzureContentSafetyProvider(
                endpoint=settings.content_safety_endpoint
            )
        else:
            content_safety_provider = MockContentSafetyProvider()
        content_safety_policy = ContentSafetyPolicy(dict(settings.content_safety_thresholds))

    ceilings = (
        {name: tenant_registry.get(name).token_budget_gbp for name in tenant_registry.names()}
        if tenant_registry is not None
        else None
    )
    return ModelGateway(
        provider,
        provider_name=provider_name,
        allowlist=ModelAllowlist(frozenset(settings.model_gateway_allowlist)),
        budget=TenantBudgetPolicy(
            ceilings=ceilings, default_ceiling_gbp=settings.model_gateway_daily_budget_gbp
        ),
        pricing=PricingTable(),
        timeout_seconds=settings.model_gateway_timeout_seconds,
        max_attempts=settings.model_gateway_max_attempts,
        pii_detector=pii_detector,
        pii_policy=pii_policy,
        content_safety_provider=content_safety_provider,
        content_safety_policy=content_safety_policy,
    )
