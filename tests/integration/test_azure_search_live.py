"""Live verification that Azure AI Search entitlement filtering actually blocks.

Excluded from the default test run (`pytest -m "not live_azure"`). Run via
`make live-verification` or the `live-verification.yaml` workflow_dispatch
job. Requires the index to already be populated
(`RAG_PROVIDER=azure_search AZURE_SEARCH_ENDPOINT=... python
scripts/ingest_azure_search.py`).

The entitlement-exclusion assertion is the important one: it constructs the
query from `customer-data.md`'s own text so `POL-DATA-003` is unambiguously
the top-ranked hybrid (BM25 + vector) match, then proves a caller without
`privacy.read` never sees it — not merely ranked lower, genuinely absent —
even though it would be returned first for a fully-entitled caller. A test
that only checked the happy path (entitled caller sees it) would prove
nothing about security trimming.

This suite, and the live ingest that populates the index, found two real
bugs that no mocked-SDK unit test could catch, both now fixed in
rag/azure_search.py: Azure Search rejects `#` in a document key (this
platform's chunk_id format is `{document_id}#chunk-N`), and its OData
`all()` lambda only accepts a *negative* per-element test — a positive
`search.in(...)` inside `all()`, the natural way to write "the caller holds
every role a chunk requires", is rejected outright with an
InvalidExpression error.
"""

import asyncio
import os

import pytest

from enterprise_genai_platform.rag.azure_search import AzureSearchIndex
from enterprise_genai_platform.rag.embedding import LocalHashEmbedding

pytestmark = pytest.mark.live_azure

_ENDPOINT = os.environ.get(
    "LIVE_AZURE_SEARCH_ENDPOINT", "https://srch-novabank-ai-dev.search.windows.net"
)
_INDEX_NAME = "novabank-policy-chunks"

# customer-data.md's own text, verbatim: with the platform's deterministic
# hash embedding, querying with a document's own content reliably makes that
# document the unambiguous top hybrid match (BM25 term overlap plus vector
# cosine similarity both favour it), which is what this test needs to prove
# exclusion is a real block, not just a lower ranking.
_CUSTOMER_DATA_QUERY = (
    "Customer information must be limited to the minimum fields required for the "
    "operational task. Contact details must remain masked in agent responses, "
    "traces, and audit records. Access to customer-data policy guidance requires "
    "both agent invocation permission and the privacy reader role. Suspected "
    "disclosure must be escalated for human review."
)


def _index() -> AzureSearchIndex:
    embedding = LocalHashEmbedding()
    return AzureSearchIndex(
        endpoint=_ENDPOINT, index_name=_INDEX_NAME, embedding_dimensions=embedding.dimensions
    )


def test_entitled_caller_retrieves_the_document() -> None:
    embedding = LocalHashEmbedding()
    index = _index()
    query_embedding = embedding.embed(_CUSTOMER_DATA_QUERY)

    hits = asyncio.run(
        index.search(
            _CUSTOMER_DATA_QUERY,
            query_embedding,
            caller_roles=frozenset({"agent.invoke", "privacy.read"}),
            limit=5,
        )
    )

    assert hits, "expected at least one hit for a fully-entitled caller"
    top_score, top_chunk = hits[0]
    assert top_chunk.document_id == "POL-DATA-003", (
        "test setup assumption violated: POL-DATA-003 must be the top-ranked "
        f"hit for a fully-entitled caller to make the exclusion test meaningful; got {hits}"
    )


def test_unentitled_caller_never_receives_the_top_ranked_document() -> None:
    """The document that ranks first for an entitled caller must be completely
    absent for a caller missing one required role — not merely re-ranked lower."""
    embedding = LocalHashEmbedding()
    index = _index()
    query_embedding = embedding.embed(_CUSTOMER_DATA_QUERY)

    unentitled_hits = asyncio.run(
        index.search(
            _CUSTOMER_DATA_QUERY,
            query_embedding,
            caller_roles=frozenset({"agent.invoke"}),
            limit=5,
        )
    )

    returned_document_ids = {chunk.document_id for _, chunk in unentitled_hits}
    assert "POL-DATA-003" not in returned_document_ids, (
        "entitlement leak: caller without privacy.read retrieved a document that requires it"
    )
    assert returned_document_ids, "other, permitted documents should still be retrievable"
