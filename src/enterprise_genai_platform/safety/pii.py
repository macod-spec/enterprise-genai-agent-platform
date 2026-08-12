"""Presidio-backed PII detection and masking.

Detection only: `presidio-anonymizer` is deliberately not a dependency because
it unconditionally pins a `cryptography` range with known CVEs. Masking here is
a simple, audit-safe span substitution over Presidio's detection results.
"""

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_analyzer.nlp_engine import NlpEngineProvider
from pydantic import BaseModel, ConfigDict, Field

_UK_SORT_CODE_PATTERN = Pattern(name="uk_sort_code", regex=r"\b\d{2}-\d{2}-\d{2}\b", score=0.7)


class PiiBlockedError(RuntimeError):
    """Raised when content contains an entity type the policy refuses to process."""

    def __init__(self, message: str, *, entity_types: tuple[str, ...]) -> None:
        super().__init__(message)
        self.entity_types = entity_types


class PiiFinding(BaseModel):
    """Audit-safe summary of one detection; the matched text is never retained."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_type: str
    score: float = Field(ge=0.0, le=1.0)


class PiiScanResult(BaseModel):
    """Sanitized text plus an audit trail that carries no raw PII values."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sanitized_text: str
    findings: tuple[PiiFinding, ...]


class PiiPolicy:
    """Per-entity mask/block decisions and the confidence floor to act on."""

    def __init__(
        self,
        *,
        mask_entities: frozenset[str],
        block_entities: frozenset[str],
        score_threshold: float = 0.5,
    ) -> None:
        if not 0.0 <= score_threshold <= 1.0:
            raise ValueError("score_threshold must be between 0 and 1")
        if mask_entities & block_entities:
            raise ValueError("An entity type cannot be both masked and blocked")
        self.mask_entities = mask_entities
        self.block_entities = block_entities
        self.score_threshold = score_threshold

    @property
    def all_entities(self) -> frozenset[str]:
        return self.mask_entities | self.block_entities


class PresidioPiiDetector:
    """Detect and mask PII using a small local spaCy model; no network calls."""

    def __init__(self) -> None:
        provider = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
            }
        )
        self._analyzer = AnalyzerEngine(
            nlp_engine=provider.create_engine(), supported_languages=["en"]
        )
        self._analyzer.registry.add_recognizer(
            PatternRecognizer(supported_entity="UK_SORT_CODE", patterns=[_UK_SORT_CODE_PATTERN])
        )

    def scan(self, text: str, policy: PiiPolicy) -> PiiScanResult:
        """Mask policy-configured entities; raise PiiBlockedError for blocked ones."""
        if not text or not policy.all_entities:
            return PiiScanResult(sanitized_text=text, findings=())

        results = self._analyzer.analyze(
            text=text,
            language="en",
            entities=sorted(policy.all_entities),
            score_threshold=policy.score_threshold,
        )
        blocked_types = sorted(
            {r.entity_type for r in results if r.entity_type in policy.block_entities}
        )
        if blocked_types:
            raise PiiBlockedError(
                f"Content contains disallowed entity types: {blocked_types}",
                entity_types=tuple(blocked_types),
            )

        # Apply the highest-confidence, left-to-right, non-overlapping spans.
        ordered = sorted(results, key=lambda r: (r.start, -r.score))
        findings: list[PiiFinding] = []
        replacements: list[tuple[int, int, str]] = []
        occupied_until = -1
        for result in ordered:
            if result.start < occupied_until:
                continue
            replacements.append((result.start, result.end, f"<{result.entity_type}>"))
            findings.append(PiiFinding(entity_type=result.entity_type, score=result.score))
            occupied_until = result.end

        sanitized = text
        for start, end, placeholder in sorted(replacements, key=lambda item: item[0], reverse=True):
            sanitized = sanitized[:start] + placeholder + sanitized[end:]

        return PiiScanResult(sanitized_text=sanitized, findings=tuple(findings))
