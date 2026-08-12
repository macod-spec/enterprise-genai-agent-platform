"""Content safety detection and severity-threshold policy enforcement.

The mock provider is a deterministic, free keyword classifier for local
development and CI. It is not a real safety classifier and must never be used
to make a genuine safety decision; production traffic should use
`AzureContentSafetyProvider` (`safety/azure_content_safety.py`).
"""

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

ContentSafetyCategory = Literal["Hate", "SelfHarm", "Sexual", "Violence"]


class ContentSafetyBlockedError(RuntimeError):
    """Raised when analyzed content meets or exceeds a policy severity threshold."""

    def __init__(self, message: str, *, findings: tuple["ContentSafetyFinding", ...]) -> None:
        super().__init__(message)
        self.findings = findings


class ContentSafetyFinding(BaseModel):
    """Audit-safe category/severity pair; the analyzed text is never retained."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: ContentSafetyCategory
    severity: int = Field(ge=0, le=7)


class ContentSafetyPolicy:
    """Per-category severity thresholds; a category at or above its threshold blocks."""

    def __init__(self, thresholds: dict[str, int]) -> None:
        if not thresholds:
            raise ValueError("At least one category threshold is required")
        if any(not 0 <= value <= 7 for value in thresholds.values()):
            raise ValueError("Severity thresholds must be between 0 and 7")
        self._thresholds = dict(thresholds)

    def blocked_findings(
        self, findings: tuple[ContentSafetyFinding, ...]
    ) -> tuple[ContentSafetyFinding, ...]:
        return tuple(
            finding
            for finding in findings
            if finding.severity >= self._thresholds.get(finding.category, 8)
        )


class ContentSafetyProvider(Protocol):
    """Minimal capability every content-safety adapter must implement."""

    async def check(self, text: str) -> tuple[ContentSafetyFinding, ...]:
        """Return a severity score (0-7) per analyzed category."""
        ...


class MockContentSafetyProvider:
    """Deterministic, free keyword classifier; not a substitute for Azure Content Safety."""

    _SIGNALS: dict[ContentSafetyCategory, tuple[str, ...]] = {
        "Hate": ("hate speech", "racial slur"),
        "SelfHarm": ("kill myself", "suicide", "self harm"),
        "Sexual": ("explicit sexual content",),
        "Violence": ("kill you", "bomb threat", "mass shooting"),
    }

    async def check(self, text: str) -> tuple[ContentSafetyFinding, ...]:
        normalized = text.casefold()
        return tuple(
            ContentSafetyFinding(
                category=category,
                severity=6 if any(marker in normalized for marker in markers) else 0,
            )
            for category, markers in self._SIGNALS.items()
        )
