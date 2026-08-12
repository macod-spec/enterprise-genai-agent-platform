"""Deterministic groundedness scoring for RAG answers against retrieved evidence.

Rule-based rather than an LLM-judge: reproducible in CI without a live model
call, and every score is explainable (which terms an answer did or did not
share with its evidence; which citations, if any, do not exist in that
evidence). This is an evaluation concern, not a policy gate: it never blocks
a response the way the PII (ADR-009) or content-safety (ADR-010) guards do.
"""

import re

from pydantic import BaseModel, ConfigDict, Field

from enterprise_genai_platform.rag.models import RetrievalResult

_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "is",
        "are",
        "was",
        "were",
        "be",
        "this",
        "that",
        "it",
        "as",
        "by",
        "with",
        "at",
        "from",
        "not",
        "does",
        "do",
        "did",
        "if",
        "so",
        "must",
        "may",
    }
)
_CITATION_PATTERN = re.compile(r"\[([A-Za-z0-9\-]+#chunk-\d+)\]")


def _significant_terms(text: str) -> frozenset[str]:
    tokens = re.findall(r"[a-z0-9]+", text.casefold())
    return frozenset(token for token in tokens if len(token) > 2 and token not in _STOPWORDS)


class GroundednessReport(BaseModel):
    """Audit-safe groundedness signals; never includes the answer or evidence text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    term_overlap_score: float = Field(ge=0.0, le=1.0)
    citations_found: tuple[str, ...]
    fabricated_citations: tuple[str, ...]
    is_grounded: bool


class GroundednessEvaluator:
    """Score whether an answer's claims and citations are supported by its evidence."""

    def __init__(self, *, minimum_term_overlap: float = 0.5) -> None:
        if not 0.0 <= minimum_term_overlap <= 1.0:
            raise ValueError("minimum_term_overlap must be between 0 and 1")
        self._minimum_term_overlap = minimum_term_overlap

    def evaluate(self, answer: str, evidence: RetrievalResult) -> GroundednessReport:
        """Return term-overlap, citation-correctness and a composite pass/fail signal."""
        known_chunk_ids = {hit.citation.chunk_id for hit in evidence.hits}
        cited = tuple(sorted(set(_CITATION_PATTERN.findall(answer))))
        fabricated = tuple(sorted(set(cited) - known_chunk_ids))

        # Citation brackets (chunk ids) are scored separately above; stripping
        # them here stops tokens like "pol" or "chunk" from diluting the
        # prose-level term-overlap signal.
        prose = _CITATION_PATTERN.sub("", answer)
        answer_terms = _significant_terms(prose)
        evidence_terms: set[str] = set()
        for hit in evidence.hits:
            evidence_terms |= _significant_terms(hit.text)

        term_overlap_score = (
            round(len(answer_terms & evidence_terms) / len(answer_terms), 4)
            if answer_terms
            else 0.0
        )

        is_grounded = (
            term_overlap_score >= self._minimum_term_overlap and bool(cited) and not fabricated
        )
        return GroundednessReport(
            term_overlap_score=term_overlap_score,
            citations_found=cited,
            fabricated_citations=fabricated,
            is_grounded=is_grounded,
        )
