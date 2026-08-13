"""Validated knowledge-document, chunk, and citation models."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Classification = Literal["public-synthetic", "internal-synthetic"]


class ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class KnowledgeDocument(ImmutableModel):
    document_id: str = Field(pattern=r"^POL-[A-Z]+-\d{3}$")
    title: str = Field(min_length=1, max_length=200)
    version: str = Field(pattern=r"^\d+\.\d+$")
    classification: Classification
    allowed_roles: frozenset[str]
    content: str = Field(min_length=20, max_length=50_000)
    provenance_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class KnowledgeChunk(ImmutableModel):
    chunk_id: str
    document_id: str
    title: str
    version: str
    classification: Classification
    allowed_roles: frozenset[str]
    text: str
    provenance_sha256: str
    embedding: tuple[float, ...]


class Citation(ImmutableModel):
    document_id: str
    chunk_id: str
    title: str
    version: str
    provenance_sha256: str


class RetrievalHit(ImmutableModel):
    text: str
    score: float = Field(ge=-1.0, le=1.0)
    citation: Citation


class RetrievalResult(ImmutableModel):
    hits: tuple[RetrievalHit, ...]
