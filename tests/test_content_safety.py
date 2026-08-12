"""Mock content-safety provider and severity-threshold policy tests (ADR-010)."""

import asyncio

import pytest

from enterprise_genai_platform.safety.content_safety import (
    ContentSafetyPolicy,
    MockContentSafetyProvider,
)


def policy(**overrides: object) -> ContentSafetyPolicy:
    thresholds: dict[str, int] = {"Hate": 4, "SelfHarm": 4, "Sexual": 4, "Violence": 4}
    thresholds.update(overrides)  # type: ignore[arg-type]
    return ContentSafetyPolicy(thresholds)


def test_mock_provider_reports_zero_severity_for_benign_text() -> None:
    findings = asyncio.run(
        MockContentSafetyProvider().check("What is the current interest rate on savings accounts?")
    )

    assert {finding.category for finding in findings} == {"Hate", "SelfHarm", "Sexual", "Violence"}
    assert all(finding.severity == 0 for finding in findings)


def test_mock_provider_flags_violence_signal() -> None:
    findings = asyncio.run(MockContentSafetyProvider().check("I will set off a bomb threat"))

    violence = next(f for f in findings if f.category == "Violence")
    assert violence.severity > 0


def test_policy_blocks_findings_at_or_above_threshold() -> None:
    findings = asyncio.run(MockContentSafetyProvider().check("this is a bomb threat"))

    blocked = policy().blocked_findings(findings)

    assert {finding.category for finding in blocked} == {"Violence"}


def test_policy_does_not_block_findings_below_threshold() -> None:
    findings = asyncio.run(MockContentSafetyProvider().check("this is a bomb threat"))

    blocked = policy(Violence=7).blocked_findings(findings)

    assert blocked == ()


def test_policy_rejects_empty_thresholds() -> None:
    with pytest.raises(ValueError, match="At least one category"):
        ContentSafetyPolicy({})


def test_policy_rejects_out_of_range_threshold() -> None:
    with pytest.raises(ValueError, match="between 0 and 7"):
        ContentSafetyPolicy({"Hate": 9})
