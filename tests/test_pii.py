"""Presidio-backed PII detection, masking and blocking policy tests."""

import pytest

from enterprise_genai_platform.safety.pii import PiiBlockedError, PiiPolicy, PresidioPiiDetector

_DETECTOR = PresidioPiiDetector()


def policy(**overrides: object) -> PiiPolicy:
    values: dict[str, object] = {
        "mask_entities": frozenset({"PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "IP_ADDRESS"}),
        "block_entities": frozenset({"CREDIT_CARD", "IBAN_CODE", "US_SSN", "UK_SORT_CODE"}),
    }
    values.update(overrides)
    return PiiPolicy(**values)  # type: ignore[arg-type]


def test_scan_masks_configured_entities_without_leaking_original_values() -> None:
    result = _DETECTOR.scan("Contact Jane Doe at jane.doe@example.com about her account.", policy())

    assert "Jane Doe" not in result.sanitized_text
    assert "jane.doe@example.com" not in result.sanitized_text
    assert "<PERSON>" in result.sanitized_text
    assert "<EMAIL_ADDRESS>" in result.sanitized_text
    assert {finding.entity_type for finding in result.findings} == {"PERSON", "EMAIL_ADDRESS"}
    assert all(0.0 <= finding.score <= 1.0 for finding in result.findings)


def test_scan_blocks_configured_entities_and_reports_types_not_values() -> None:
    with pytest.raises(PiiBlockedError) as exc_info:
        _DETECTOR.scan("My card number is 4111 1111 1111 1111, please charge it.", policy())

    assert exc_info.value.entity_types == ("CREDIT_CARD",)
    assert "4111 1111 1111 1111" not in str(exc_info.value)


def test_scan_detects_custom_uk_sort_code_recognizer() -> None:
    with pytest.raises(PiiBlockedError) as exc_info:
        _DETECTOR.scan("Please pay into sort code 12-34-56, account 12345678.", policy())

    assert "UK_SORT_CODE" in exc_info.value.entity_types


def test_scan_leaves_text_without_pii_unchanged() -> None:
    result = _DETECTOR.scan("What is the current interest rate on savings accounts?", policy())

    assert result.sanitized_text == "What is the current interest rate on savings accounts?"
    assert result.findings == ()


def test_scan_returns_unchanged_text_when_no_entities_configured() -> None:
    result = _DETECTOR.scan(
        "Contact jane.doe@example.com",
        policy(mask_entities=frozenset(), block_entities=frozenset()),
    )

    assert result.sanitized_text == "Contact jane.doe@example.com"
    assert result.findings == ()


def test_policy_rejects_overlapping_mask_and_block_entities() -> None:
    with pytest.raises(ValueError, match="cannot be both masked and blocked"):
        policy(mask_entities=frozenset({"CREDIT_CARD"}), block_entities=frozenset({"CREDIT_CARD"}))


def test_policy_rejects_invalid_score_threshold() -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        policy(score_threshold=1.5)
