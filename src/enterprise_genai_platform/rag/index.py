"""Local vector index with mandatory metadata authorization filters."""

from enterprise_genai_platform.rag.models import KnowledgeChunk


class LocalVectorIndex:
    """Immutable-at-query vector index; replaceable by Azure AI Search later."""

    def __init__(self) -> None:
        self._chunks: dict[str, KnowledgeChunk] = {}

    def add(self, chunks: tuple[KnowledgeChunk, ...]) -> None:
        for chunk in chunks:
            if chunk.chunk_id in self._chunks:
                raise ValueError(f"Duplicate knowledge chunk: {chunk.chunk_id}")
            self._chunks[chunk.chunk_id] = chunk

    def search(
        self,
        query_embedding: tuple[float, ...],
        *,
        caller_roles: frozenset[str],
        limit: int,
    ) -> tuple[tuple[float, KnowledgeChunk], ...]:
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
