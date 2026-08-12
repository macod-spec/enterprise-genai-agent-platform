"""Server-side entitlement filter and Azure AI Search adapter tests (ADR-011)."""

import pytest

from enterprise_genai_platform.gateway.config import Settings
from enterprise_genai_platform.rag import build_default_retriever, build_retriever
from enterprise_genai_platform.rag.azure_search import AzureSearchIndex, build_role_filter


def test_role_filter_requires_all_chunk_roles_to_be_held_by_caller() -> None:
    single = build_role_filter(frozenset({"agent.invoke"}))
    multi = build_role_filter(frozenset({"agent.invoke", "privacy.read"}))

    assert single == "allowed_roles/all(r: search.in(r, 'agent.invoke', '|'))"
    assert "search.in(r, 'agent.invoke|privacy.read', '|')" in multi
    assert multi.startswith("allowed_roles/all(")


def test_role_filter_denies_by_default_when_caller_has_no_roles() -> None:
    empty_filter = build_role_filter(frozenset())

    assert empty_filter == "allowed_roles/all(r: search.in(r, '', '|'))"


def test_role_filter_escapes_embedded_quotes() -> None:
    filtered = build_role_filter(frozenset({"weird'role"}))

    assert "weird''role" in filtered
    assert "weird'role" not in filtered.replace("weird''role", "")


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
