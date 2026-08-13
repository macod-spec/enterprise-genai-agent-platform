"""Cross-tenant leakage test — written and run first, before any implementation.

Per the multi-tenancy build order: this test is the proof of the entire
design and is written against the target API before that API exists, so it
fails for real reasons rather than being retrofitted by someone who already
knows how the implementation works and will unconsciously write around its
own weaknesses. Do not weaken an assertion here to make the implementation
easier; fix the implementation.

Two tenants throughout: `payment-disputes` (tenant A) and `complaints-triage`
(tenant B), per config/tenants/*.yaml. Six things tenant A must never be able
to do:

1. Read tenant B's approval/workflow state.
2. Retrieve tenant B's documents — including when a B-only document is the
   top semantic match for A's query. This is the point that matters most: a
   test that only checks the happy path proves nothing about security
   trimming.
3. Consume tenant B's token budget.
4. See tenant B's metrics or traces (no unlabelled series either).
5. See a skill granted only to tenant B.
6. Set its own tenant identity to B through any client-controllable input
   (request body, query parameter, or a second/conflicting header).
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from enterprise_genai_platform.gateway.app import create_app
from enterprise_genai_platform.gateway.config import Settings
from enterprise_genai_platform.model_gateway.contracts import ModelBudgetExceeded
from enterprise_genai_platform.model_gateway.policy import TenantBudgetPolicy
from enterprise_genai_platform.rag import build_default_retriever
from enterprise_genai_platform.state import build_approval_store
from enterprise_genai_platform.tenancy.context import TenantContext
from enterprise_genai_platform.tenancy.registry import (
    UnknownTenantError,
    build_default_tenant_registry,
)

TENANT_A = "payment-disputes"
TENANT_B = "complaints-triage"

# customer-data.md's own text reliably makes it the top hybrid match under the
# platform's deterministic embedding — the same trick used in
# tests/integration/test_azure_search_live.py. Here it is a B-only document.
_B_ONLY_QUERY = (
    "A complaint must be acknowledged within one business day and assigned a "
    "case owner before triage begins. Complaints alleging financial loss or "
    "referencing a regulator must be escalated to the complaints-triage senior "
    "review queue immediately, not held in standard triage."
)


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {"app_env": "test", "rate_limit_requests": 100}
    values.update(overrides)
    return Settings.model_validate(values)


def _headers(*, tenant: str, user: str = "tester", roles: str = "agent.invoke") -> dict[str, str]:
    return {"X-Local-User": user, "X-Local-Roles": roles, "X-Local-Tenant": tenant}


def test_tenant_registry_loads_the_three_real_bundles() -> None:
    registry = build_default_tenant_registry()

    assert registry.get(TENANT_A).name == TENANT_A
    assert registry.get(TENANT_B).name == TENANT_B
    with pytest.raises(UnknownTenantError):
        registry.get("not-a-real-tenant")


# --- 1. State / workflow threads -------------------------------------------


def test_tenant_a_cannot_list_tenant_bs_pending_approvals() -> None:
    store = build_approval_store("sqlite", sqlite_path=":memory:", connection_url=None)
    store.create_pending(request_id="req-b-1", requester="b-user", query="q", tenant=TENANT_B)
    store.create_pending(request_id="req-a-1", requester="a-user", query="q", tenant=TENANT_A)

    a_records = store.list_pending(tenant=TENANT_A)

    assert len(a_records) == 1
    assert all(record.tenant == TENANT_A for record in a_records)
    assert not any(record.request_id == "req-b-1" for record in a_records)


# --- 2. Retrieval: the point that matters most ------------------------------


def test_tenant_a_never_retrieves_the_top_ranked_b_only_document() -> None:
    async def _run() -> None:
        registry = build_default_tenant_registry()
        retriever = build_default_retriever()
        tenant_a = TenantContext(tenant=TENANT_A, bundle=registry.get(TENANT_A))
        tenant_b = TenantContext(tenant=TENANT_B, bundle=registry.get(TENANT_B))

        # Assumption check: the B-only document must be the unambiguous top
        # match for a fully-entitled caller, or excluding it proves nothing.
        b_side = await retriever.retrieve(_B_ONLY_QUERY, caller_roles=tenant_b.bundle.entitlements)
        assert b_side.hits, "expected at least one hit for tenant B"
        assert b_side.hits[0].citation.document_id == "POL-CMP-005", (
            "test setup assumption violated: POL-CMP-005 must be the top-ranked "
            f"hit for tenant B to make the exclusion test meaningful; got {b_side.hits}"
        )

        a_side = await retriever.retrieve(_B_ONLY_QUERY, caller_roles=tenant_a.bundle.entitlements)
        a_document_ids = {hit.citation.document_id for hit in a_side.hits}
        assert "POL-CMP-005" not in a_document_ids, (
            "entitlement leak: tenant A retrieved a document scoped to tenant B"
        )

    asyncio.run(_run())


# --- 3. Token budget ---------------------------------------------------------


def test_tenant_bs_budget_exhaustion_does_not_affect_tenant_a() -> None:
    registry = build_default_tenant_registry()
    tenant_a = registry.get(TENANT_A)
    tenant_b = registry.get(TENANT_B)
    policy = TenantBudgetPolicy(
        ceilings={TENANT_A: tenant_a.token_budget_gbp, TENANT_B: tenant_b.token_budget_gbp}
    )

    with pytest.raises(ModelBudgetExceeded):
        policy.check_and_reserve(TENANT_B, tenant_b.token_budget_gbp + 0.01)

    # Tenant A's independent budget must be untouched by B's exhaustion.
    policy.check_and_reserve(TENANT_A, 0.01)


# --- 4. Metrics and traces ---------------------------------------------------


def test_model_gateway_metrics_are_labelled_by_tenant_not_shared() -> None:
    from enterprise_genai_platform.metrics import MODEL_GATEWAY_CALLS

    # Checked against the label names declared at metric-construction time,
    # not a live sample: a Counter reports no samples at all until its first
    # .labels(...).inc(), so relying on collect() here would pass trivially
    # for the wrong reason (no calls made yet) rather than the right one
    # (tenant is genuinely part of the label schema).
    assert "tenant" in MODEL_GATEWAY_CALLS._labelnames, (
        "MODEL_GATEWAY_CALLS must carry a tenant label so per-tenant cost is "
        "attributable and one tenant's usage is never folded into another's"
    )


# --- 5. Skills ---------------------------------------------------------------


def test_tenant_a_does_not_see_a_skill_scoped_only_to_tenant_b() -> None:
    app = create_app(_settings())
    client = TestClient(app)

    response = client.get(
        "/api/v1/skills", headers=_headers(tenant=TENANT_A, roles="platform.viewer")
    )

    assert response.status_code == 200
    skill_names = {skill["name"] for skill in response.json()["skills"]}
    registry = build_default_tenant_registry()
    b_only_skills = registry.get(TENANT_B).allowed_skills - registry.get(TENANT_A).allowed_skills
    assert not (skill_names & b_only_skills), "tenant A can see a tenant-B-only skill"


# --- 6. Client-controlled tenant override ------------------------------------


def test_tenant_a_cannot_set_tenant_b_via_request_body() -> None:
    app = create_app(_settings())
    client = TestClient(app)

    response = client.post(
        "/api/v1/workflows/investigate",
        headers=_headers(tenant=TENANT_A),
        json={"query": "Look up account status for customer CUST-1098", "tenant": TENANT_B},
    )

    # A body field named "tenant" must be rejected or silently ignored — never
    # honoured. RouteRequest's extra="forbid" should reject the unknown field
    # outright; that is an acceptable way to fail this attack, not just a 200
    # that quietly used tenant A anyway.
    assert response.status_code in (200, 422)
    if response.status_code == 200:
        # If accepted, the effective tenant must still have been A. There is
        # no tenant field in InvestigationResponse to check directly, so this
        # is asserted at the metrics layer in a dedicated integration test
        # once tenant-labelled metrics exist; a 422 (extra field forbidden)
        # is the expected, simpler outcome given RouteRequest's schema.
        pytest.fail("investigate accepted an unknown 'tenant' body field instead of rejecting it")


def test_tenant_a_cannot_set_tenant_b_via_query_parameter() -> None:
    app = create_app(_settings())
    client = TestClient(app)

    response = client.get(
        "/api/v1/skills?tenant=complaints-triage",
        headers=_headers(tenant=TENANT_A, roles="platform.viewer"),
    )

    assert response.status_code == 200
    skill_names = {skill["name"] for skill in response.json()["skills"]}
    registry = build_default_tenant_registry()
    b_only_skills = registry.get(TENANT_B).allowed_skills - registry.get(TENANT_A).allowed_skills
    assert not (skill_names & b_only_skills), (
        "a ?tenant= query parameter overrode the header-resolved tenant"
    )


def test_missing_tenant_header_is_rejected_not_defaulted() -> None:
    """No implicit tenant. Omitting X-Local-Tenant must fail closed, not
    silently fall back to some default tenant that would itself be a leakage
    vector for every tenant that forgets to set the header."""
    app = create_app(_settings())
    client = TestClient(app)

    response = client.get(
        "/api/v1/skills",
        headers={"X-Local-User": "tester", "X-Local-Roles": "platform.viewer"},
    )

    assert response.status_code in (400, 401, 403)
