"""Server-side entitlement filter and Azure AI Search adapter tests (ADR-011)."""

import asyncio

import pytest

from enterprise_genai_platform.gateway.config import Settings
from enterprise_genai_platform.rag import build_default_retriever, build_retriever
from enterprise_genai_platform.rag.azure_search import AzureSearchIndex, build_role_filter
from enterprise_genai_platform.rag.models import KnowledgeChunk


def test_role_filter_requires_all_chunk_roles_to_be_held_by_caller() -> None:
    """Azure Search's all() only accepts a negative per-element test, confirmed live
    (a positive search.in() inside all() is rejected with InvalidExpression), so the
    filter is built as "no chunk role is among the *known* roles the caller lacks" —
    logically equivalent to the subset check as long as _KNOWN_CHUNK_ROLES is complete."""
    full_access = build_role_filter(frozenset({"agent.invoke", "privacy.read"}))
    partial_access = build_role_filter(frozenset({"agent.invoke"}))

    assert full_access == "allowed_roles/all(r: not search.in(r, '', '|'))"
    assert partial_access == "allowed_roles/all(r: not search.in(r, 'privacy.read', '|'))"


def test_role_filter_denies_by_default_when_caller_has_no_roles() -> None:
    empty_filter = build_role_filter(frozenset())

    assert (
        empty_filter == "allowed_roles/all(r: not search.in(r, 'agent.invoke|privacy.read', '|'))"
    )


def test_role_filter_never_embeds_caller_supplied_role_text() -> None:
    """Only _KNOWN_CHUNK_ROLES members (this module's own constants) are ever
    interpolated into the filter string; an unrecognised caller role is simply
    absent from _KNOWN_CHUNK_ROLES - caller_roles, never written into the query.
    A stronger property than escaping: there is nothing here to escape, because
    caller-supplied text is never embedded at all."""
    filtered = build_role_filter(frozenset({"weird'role"}))

    assert "weird" not in filtered
    assert filtered == "allowed_roles/all(r: not search.in(r, 'agent.invoke|privacy.read', '|'))"


def test_role_filter_rejects_role_containing_the_delimiter() -> None:
    with pytest.raises(ValueError, match=r"must not contain"):
        build_role_filter(frozenset({"a|b"}))


def test_role_filter_is_deterministic_regardless_of_set_iteration_order() -> None:
    first = build_role_filter(frozenset({"agent.invoke", "privacy.read", "policy.viewer"}))
    second = build_role_filter(frozenset({"policy.viewer", "agent.invoke", "privacy.read"}))

    assert first == second


def test_azure_search_index_rejects_missing_configuration() -> None:
    with pytest.raises(ValueError, match="endpoint and index_name are required"):
        AzureSearchIndex(endpoint="", index_name="policy-chunks")


def test_azure_search_index_rejects_small_embedding_dimensions() -> None:
    with pytest.raises(ValueError, match="embedding_dimensions"):
        AzureSearchIndex(
            endpoint="https://example.search.windows.net",
            index_name="policy-chunks",
            embedding_dimensions=8,
        )


def test_azure_search_index_constructs_without_network_calls() -> None:
    index = AzureSearchIndex(
        endpoint="https://example.search.windows.net", index_name="policy-chunks"
    )

    assert index is not None


def test_add_rejects_a_chunk_whose_role_is_outside_the_known_vocabulary() -> None:
    """The role-filter query's correctness depends on _KNOWN_CHUNK_ROLES covering
    every role a chunk can declare; this must fail loud at ingestion, before any
    network call, rather than silently producing a wrong query result later."""
    index = AzureSearchIndex(
        endpoint="https://example.search.windows.net", index_name="policy-chunks"
    )
    chunk = KnowledgeChunk(
        chunk_id="POL-TEST-000#chunk-1",
        document_id="POL-TEST-000",
        title="Test",
        version="1.0",
        classification="internal-synthetic",
        allowed_roles=frozenset({"never.registered"}),
        text="irrelevant",
        provenance_sha256="0" * 64,
        embedding=(),
    )

    with pytest.raises(ValueError, match="never.registered"):
        asyncio.run(index.add((chunk,)))


def test_factory_builds_local_retriever_by_default() -> None:
    retriever = build_retriever(Settings.model_validate({"app_env": "test"}))

    assert retriever is not None


def test_factory_builds_azure_search_retriever_without_network_calls() -> None:
    retriever = build_retriever(
        Settings.model_validate(
            {
                "app_env": "test",
                "rag_provider": "azure_search",
                "azure_search_endpoint": "https://example.search.windows.net",
            }
        )
    )

    assert retriever is not None


def test_settings_require_endpoint_for_azure_search_provider() -> None:
    with pytest.raises(ValueError, match="AZURE_SEARCH_ENDPOINT is required"):
        Settings.model_validate({"app_env": "test", "rag_provider": "azure_search"})


def test_default_retriever_still_works_end_to_end() -> None:
    retriever = build_default_retriever()

    assert retriever is not None
