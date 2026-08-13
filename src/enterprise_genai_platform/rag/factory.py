"""Build the bundled, offline NovaBank policy knowledge base."""

from importlib.resources import files

from enterprise_genai_platform.gateway.config import Settings
from enterprise_genai_platform.rag.azure_search import AzureSearchIndex
from enterprise_genai_platform.rag.embedding import LocalHashEmbedding
from enterprise_genai_platform.rag.index import LocalVectorIndex
from enterprise_genai_platform.rag.ingestion import parse_policy_document
from enterprise_genai_platform.rag.models import KnowledgeChunk, KnowledgeDocument
from enterprise_genai_platform.rag.retrieval import AuthorizedRetriever


def chunk_document(
    document: KnowledgeDocument,
    embedding: LocalHashEmbedding,
    *,
    chunk_size: int = 500,
    overlap: int = 80,
) -> tuple[KnowledgeChunk, ...]:
    if chunk_size < 100 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("Chunking configuration is invalid")
    chunks: list[KnowledgeChunk] = []
    start = 0
    index = 1
    while start < len(document.content):
        end = min(start + chunk_size, len(document.content))
        if end < len(document.content):
            boundary = document.content.rfind(" ", start, end)
            if boundary > start:
                end = boundary
        text = document.content[start:end].strip()
        if text:
            chunks.append(
                KnowledgeChunk(
                    chunk_id=f"{document.document_id}#chunk-{index}",
                    document_id=document.document_id,
                    title=document.title,
                    version=document.version,
                    classification=document.classification,
                    allowed_roles=document.allowed_roles,
                    text=text,
                    provenance_sha256=document.provenance_sha256,
                    embedding=embedding.embed(text),
                )
            )
            index += 1
        if end == len(document.content):
            break
        start = end - overlap
    return tuple(chunks)


def build_default_retriever() -> AuthorizedRetriever:
    embedding = LocalHashEmbedding()
    index = LocalVectorIndex()
    document_directory = files("enterprise_genai_platform.rag").joinpath("documents")
    for resource in sorted(document_directory.iterdir(), key=lambda item: item.name):
        if resource.name.endswith(".md"):
            document = parse_policy_document(resource.read_bytes(), source_name=resource.name)
            index.add(chunk_document(document, embedding))
    return AuthorizedRetriever(index, embedding)


def build_retriever(settings: Settings) -> AuthorizedRetriever:
    """Select the configured retrieval backend (ADR-011).

    `local` indexes the bundled documents in-process at startup. `azure_search`
    assumes an index that is already created and populated by a separate,
    offline ingestion step (`scripts/ingest_azure_search.py`); the serving
    path here never mutates the index, only queries it.
    """
    if settings.rag_provider == "azure_search":
        if not settings.azure_search_endpoint:
            raise ValueError("Azure AI Search endpoint is required for the azure_search provider")
        index = AzureSearchIndex(
            endpoint=settings.azure_search_endpoint,
            index_name=settings.azure_search_index_name,
        )
        return AuthorizedRetriever(index, LocalHashEmbedding())
    return build_default_retriever()
