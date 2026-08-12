"""Local vector index with mandatory metadata authorization filters."""

from typing import Protocol

from enterprise_genai_platform.rag.models import KnowledgeChunk


class VectorIndex(Protocol):
    """Common contract for local and Azure AI Search-backed retrieval (ADR-011).

    Both the raw query text and its embedding are passed through so a hybrid
    backend can combine keyword (BM25) and vector search; a vector-only
    implementation is free to ignore the text.
    """

    async def search(
        self,
        query: str,
        query_embedding: tuple[float, ...],
        *,
        caller_roles: frozenset[str],
        limit: int,
    ) -> tuple[tuple[float, KnowledgeChunk], ...]:
        """Return authorized (score, chunk) pairs; filtering never happens client-side."""
        ...


class LocalVectorIndex:
    """In-memory reference implementation of VectorIndex for local development and CI."""

    def __init__(self) -> None:
        self._chunks: dict[str, KnowledgeChunk] = {}

    def add(self, chunks: tuple[KnowledgeChunk, ...]) -> None:
        for chunk in chunks:
            if chunk.chunk_id in self._chunks:
                raise ValueError(f"Duplicate knowledge chunk: {chunk.chunk_id}")
            self._chunks[chunk.chunk_id] = chunk

    async def search(
        self,
        query: str,
        query_embedding: tuple[float, ...],
        *,
        caller_roles: frozenset[str],
        limit: int,
    ) -> tuple[tuple[float, KnowledgeChunk], ...]:
        del query  # vector-only; a hybrid backend uses this for keyword search
        candidates = (
            (self._similarity(query_embedding, chunk.embedding), chunk)
            for chunk in self._chunks.values()
            if chunk.allowed_roles <= caller_roles
        )
        ranked = sorted(candidates, key=lambda item: (-item[0], item[1].chunk_id))
        return tuple(item for item in ranked if item[0] > 0)[:limit]

    @staticmethod
    def _similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
        if len(left) != len(right):
            raise ValueError("Embedding dimensions do not match")
        return sum(a * b for a, b in zip(left, right, strict=True))
