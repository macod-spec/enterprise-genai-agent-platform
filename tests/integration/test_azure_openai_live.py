"""Live verification that the Azure OpenAI adapter actually works against Azure.

Excluded from the default test run (`pytest -m "not live_azure"`, the default
addopts) because it makes real network calls, spends real (if tiny) money, and
requires `az login` / a workload identity with `Cognitive Services OpenAI User`
on a real deployment. Run explicitly with `make live-verification` or the
`live-verification.yaml` workflow_dispatch job.

Unit tests cannot catch what this catches: they mock the OpenAI SDK client, so
a wrong parameter name, an unsupported parameter value, a token scope typo, or
an RBAC gap all pass silently. This test found two real bugs in
`azure_openai.py` before being written to be green: the adapter sent the
deprecated `max_tokens` (rejected outright by reasoning-family models) and an
explicit `temperature=0.0` (also rejected by reasoning-family models, which
only support their default temperature). Both are fixed in the adapter; this
test is what would have caught them.
"""

import asyncio
import os

import pytest

from enterprise_genai_platform.model_gateway.adapters.azure_openai import AzureOpenAIChatModel
from enterprise_genai_platform.model_gateway.contracts import ChatMessage, ModelGenerationRequest
from enterprise_genai_platform.model_gateway.gateway import ModelGateway
from enterprise_genai_platform.model_gateway.policy import ModelAllowlist, TenantBudgetPolicy
from enterprise_genai_platform.model_gateway.pricing import PricingTable

pytestmark = pytest.mark.live_azure

_ENDPOINT = os.environ.get(
    "LIVE_AZURE_OPENAI_ENDPOINT", "https://oai-novabank-ai-dev.openai.azure.com/"
)
_DEPLOYMENT = os.environ.get("LIVE_AZURE_OPENAI_DEPLOYMENT", "gpt-5-nano")
_API_VERSION = "2024-10-21"


def test_azure_openai_adapter_completes_a_real_request() -> None:
    adapter = AzureOpenAIChatModel(
        endpoint=_ENDPOINT, api_version=_API_VERSION, timeout_seconds=30.0
    )
    request = ModelGenerationRequest(
        model=_DEPLOYMENT,
        messages=(ChatMessage(role="user", content="Reply with exactly the word: pong"),),
        tenant="live-verification",
        agent="live-verification",
        max_tokens=1000,
    )

    result = asyncio.run(adapter.generate(request))

    assert result.provider == "azure_openai"
    assert result.content.strip().lower() == "pong"
    assert result.finish_reason == "stop"
    assert result.usage.prompt_tokens > 0
    assert result.usage.completion_tokens > 0
    assert result.latency_seconds > 0


def test_azure_openai_adapter_reaches_azure_through_the_governed_gateway() -> None:
    """The full call path (allowlist, budget, telemetry) must also reach Azure, not
    just the adapter in isolation."""
    adapter = AzureOpenAIChatModel(
        endpoint=_ENDPOINT, api_version=_API_VERSION, timeout_seconds=30.0
    )
    gateway = ModelGateway(
        adapter,
        provider_name="azure_openai",
        allowlist=ModelAllowlist(frozenset({_DEPLOYMENT})),
        budget=TenantBudgetPolicy(default_ceiling_gbp=1.0),
        pricing=PricingTable(),
        timeout_seconds=30.0,
        max_attempts=1,
    )
    request = ModelGenerationRequest(
        model=_DEPLOYMENT,
        messages=(ChatMessage(role="user", content="Reply with exactly the word: pong"),),
        tenant="live-verification",
        agent="live-verification",
        max_tokens=1000,
    )

    result = asyncio.run(gateway.generate(request))

    assert result.content.strip().lower() == "pong"
    assert result.estimated_cost_gbp > 0
