"""Authorized retrieval with evidence citations and provenance."""

from enterprise_genai_platform.metrics import RAG_HITS, RAG_RETRIEVALS
from enterprise_genai_platform.rag.embedding import LocalHashEmbedding
from enterprise_genai_platform.rag.index import LocalVectorIndex
from enterprise_genai_platform.rag.models import Citation, RetrievalHit, RetrievalResult


class AuthorizedRetriever:
    def __init__(self, index: LocalVectorIndex, embedding: LocalHashEmbedding) -> None:
        self._index = index
        self._embedding = embedding

    def retrieve(
        self,
        query: str,
        *,
        caller_roles: frozenset[str],
        limit: int = 3,
    ) -> RetrievalResult:
        if not query.strip() or len(query) > 500:
            raise ValueError("Retrieval query length is invalid")
        if limit < 1 or limit > 5:
            raise ValueError("Retrieval result limit is invalid")
        ranked = self._index.search(
            self._embedding.embed(query),
            caller_roles=caller_roles,
            limit=limit,
        )
        result = RetrievalResult(
            hits=tuple(
                RetrievalHit(
                    text=chunk.text,
                    score=round(score, 6),
                    citation=Citation(
                        document_id=chunk.document_id,
                        chunk_id=chunk.chunk_id,
                        title=chunk.title,
                        version=chunk.version,
                        provenance_sha256=chunk.provenance_sha256,
                    ),
                )
                for score, chunk in ranked
            )
        )
        RAG_RETRIEVALS.labels("hit" if result.hits else "empty").inc()
        RAG_HITS.observe(len(result.hits))
        return result
