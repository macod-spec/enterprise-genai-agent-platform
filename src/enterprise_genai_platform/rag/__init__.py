"""Secure local retrieval-augmented generation foundations."""

from enterprise_genai_platform.rag.factory import build_default_retriever
from enterprise_genai_platform.rag.retrieval import AuthorizedRetriever

__all__ = ["AuthorizedRetriever", "build_default_retriever"]
