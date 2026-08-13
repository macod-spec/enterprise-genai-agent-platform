"""Offline ingestion: populate Azure AI Search from the bundled NovaBank policy corpus.

Deliberately separate from the serving app (gateway/app.py): the app only
queries the index at request time (ADR-011), so index creation and document
upload happen here, on demand, not on every process start.

Requires RAG_PROVIDER=azure_search and AZURE_SEARCH_ENDPOINT to be set;
authenticates keyless via DefaultAzureCredential (`az login` locally, workload
identity in AKS). Not run in CI: no Azure AI Search resource exists in this
sandbox, so this script is implemented but has not been exercised against a
live endpoint.
"""

import asyncio
from importlib.resources import files

from enterprise_genai_platform.gateway.config import get_settings
from enterprise_genai_platform.rag.azure_search import AzureSearchIndex
from enterprise_genai_platform.rag.embedding import LocalHashEmbedding
from enterprise_genai_platform.rag.factory import chunk_document
from enterprise_genai_platform.rag.ingestion import parse_policy_document


async def main() -> None:
    settings = get_settings()
    if settings.rag_provider != "azure_search" or not settings.azure_search_endpoint:
        raise SystemExit("Set RAG_PROVIDER=azure_search and AZURE_SEARCH_ENDPOINT before ingesting")

    embedding = LocalHashEmbedding()
    index = AzureSearchIndex(
        endpoint=settings.azure_search_endpoint,
        index_name=settings.azure_search_index_name,
        embedding_dimensions=embedding.dimensions,
    )
    await index.ensure_index()

    document_directory = files("enterprise_genai_platform.rag").joinpath("documents")
    chunk_count = 0
    for resource in sorted(document_directory.iterdir(), key=lambda item: item.name):
        if not resource.name.endswith(".md"):
            continue
        document = parse_policy_document(resource.read_bytes(), source_name=resource.name)
        chunks = chunk_document(document, embedding)
        await index.add(chunks)
        chunk_count += len(chunks)
        print(f"Ingested {document.document_id}: {len(chunks)} chunk(s)")

    print(f"Done: {chunk_count} chunk(s) uploaded to index '{settings.azure_search_index_name}'")


if __name__ == "__main__":
    asyncio.run(main())
