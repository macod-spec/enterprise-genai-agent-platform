"""Live verification that the Azure Content Safety adapter actually works.

Excluded from the default test run (`pytest -m "not live_azure"`). Run via
`make live-verification` or the `live-verification.yaml` workflow_dispatch
job. Asserts both directions: a benign string must not be flagged, and a
known-harmful string must score high enough on at least one category to be
blocked by the platform's policy thresholds — proving the real classifier
behind the adapter, not just that the adapter's HTTP plumbing works.
"""

import asyncio
import os

import pytest

from enterprise_genai_platform.safety.azure_content_safety import AzureContentSafetyProvider
from enterprise_genai_platform.safety.content_safety import ContentSafetyPolicy

pytestmark = pytest.mark.live_azure

_ENDPOINT = os.environ.get(
    "LIVE_CONTENT_SAFETY_ENDPOINT", "https://cs-novabank-ai-dev.cognitiveservices.azure.com/"
)
_DEFAULT_THRESHOLDS = {"Hate": 4, "SelfHarm": 4, "Sexual": 4, "Violence": 4}


def test_benign_text_is_not_blocked() -> None:
    provider = AzureContentSafetyProvider(endpoint=_ENDPOINT)
    policy = ContentSafetyPolicy(_DEFAULT_THRESHOLDS)

    findings = asyncio.run(
        provider.check("This is a perfectly ordinary, benign customer service message.")
    )

    assert len(findings) == 4
    assert policy.blocked_findings(findings) == ()


def test_harmful_text_is_blocked() -> None:
    provider = AzureContentSafetyProvider(endpoint=_ENDPOINT)
    policy = ContentSafetyPolicy(_DEFAULT_THRESHOLDS)

    findings = asyncio.run(
        provider.check("I will find you and kill you, I have a bomb threat planned.")
    )

    blocked = policy.blocked_findings(findings)
    assert blocked, f"expected at least one blocked category, got {findings}"
    assert any(finding.category == "Violence" for finding in blocked)
