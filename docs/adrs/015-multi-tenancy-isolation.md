# ADR-015: Multi-tenancy isolation

Status: accepted

## Context

The platform's actual product is not any one agent — it is the paved road: a
governed, observable, cost-controlled substrate that lets many internal teams
run their own agents without each team re-solving auth, retrieval scoping,
budget enforcement, and audit. Proving that thesis requires more than one
team on the platform. Without real tenant isolation, "forty teams could build
on this" is a claim, not a demonstrated property, and a single shared-nothing
assumption bug (a cache key, a retrieval filter, a budget ledger) would let
one team read or spend against another's data.

Three synthetic NovaBank teams stand in for that population:
`payment-disputes`, `complaints-triage`, `kyc-review` (later joined by a
fourth, `fraud-alerts`, added specifically to verify the onboarding claim —
see Verification below). The three specialist agents (customer, payments,
policy) are capabilities the platform offers, not tenants themselves; this
work does not change what they do, only who is allowed to reach what through
them.

## Decision

### Tenant identity source

Tenant identity is resolved exactly once, at the gateway edge
(`gateway/auth.py:get_tenant_context`), from an `X-Local-Tenant` header —
the same local-identity trust model this codebase already uses for
`X-Local-User`/`X-Local-Roles` (`get_principal`), gated to `local`/`test`
`APP_ENV` and returning 503 elsewhere. This is explicitly not a real JWT
tenant claim: the codebase has no JWT validation infrastructure at all, and
shipping a half-verified one to look more finished would be worse than an
honestly-scoped local mechanism with a clear pre-production gate, consistent
with how the rest of auth in this platform is already gated. Real tenant
claims from verified Entra tokens remain a mandatory pre-production
requirement (`docs/portfolio/limitations.md`), same as caller identity
generally.

Resolution happens once and produces an immutable `TenantContext` (tenant
name plus its `TenantBundle`), threaded explicitly through every call site
that needs it — never re-derived, never read from a request body or query
parameter. `RouteRequest`'s `extra="forbid"` already rejected a
client-supplied `tenant` field in the body before this work started; the
leakage suite proves the same for a query parameter and for the `X-Local-*`
header set.

### Tenant config bundles

`config/tenants/<name>.yaml`, loaded and Pydantic-validated at startup by
`build_default_tenant_registry()`. Each bundle carries `system_prompt`,
`allowed_skills`, `model_tier`, `memory_policy`, `entitlements`,
`token_budget_gbp`, `risk_tier`, `cost_centre`. This directory is
deliberately at the repo root, not packaged inside `src/` alongside
`skills/definitions/`: it is operational configuration a platform operator
edits, not application code a developer ships (see the module docstring in
`tenancy/registry.py`).

**Zero-code rule, enforced, not just documented**: onboarding a tenant is
adding one file here. `scripts/check-tenant-drift.sh` greps `src/` for every
tenant name currently declared in `config/tenants/*.yaml` (read from the
YAML itself, not hardcoded in the script) and fails CI if any appear —
wired into `make check` and the `python-security` CI job. Tests are
deliberately out of scope for this check: the leakage suite and registry
tests legitimately assert against real tenant names, which is normal test
practice, not drift.

### State isolation — PostgreSQL Row-Level Security

RLS, not schema-per-tenant. Schema-per-tenant scales isolation blast-radius
better at very high tenant counts but multiplies migration and connection-
pooling operational surface linearly with tenant count; RLS keeps one schema
and pushes the isolation guarantee into the database engine itself, which is
the right trade for a platform whose tenant count is teams-in-an-organisation
scale, not one schema per end customer.

Two things had to be right for RLS to actually isolate anything, both
`FORCE ROW LEVEL SECURITY` implies but don't ensure alone:

1. **The stale-session-variable failure mode.** A pooled connection handed to
   tenant B after serving tenant A must carry no trace of A's tenant
   context. `_tenant_scoped_cursor` sets it via
   `SELECT set_config('app.tenant_id', %s, true)` — the parameterized
   equivalent of `SET LOCAL` — inside the same transaction as every query,
   never a bare session-scoped `SET`. Postgres resets an `is_local => true`
   setting at `COMMIT`/`ROLLBACK` regardless of what happens to the
   underlying connection afterwards, so this is structurally prevented, not
   merely tested for.
2. **The superuser/table-owner bypass.** RLS is bypassed unconditionally by
   Postgres superusers (no override exists for this) and, separately, by an
   ordinary role that owns the table — which the connecting role normally
   does, having just `CREATE TABLE`d it — unless `FORCE ROW LEVEL SECURITY`
   is also set. `PostgreSQLApprovalStore.__init__` sets both `ENABLE` and
   `FORCE`. This is not a hypothetical: the first version of
   `tests/integration/test_postgres_rls_pool.py` connected as the
   container's default `postgres` superuser and passed — silently proving
   nothing, since a superuser ignores RLS regardless of `FORCE`. The test
   fixture was rewritten to create and connect as an explicit
   `NOSUPERUSER NOBYPASSRLS` role that owns the table, which is what
   actually exercises the `FORCE` guarantee, and *that* version genuinely
   failed against the pre-fix code before passing after it.

A minimal `PostgresConnectionPool` (a `queue.Queue` wrapper around the
existing `pg8000` driver, no new dependency) is deliberately kept small in
tests — a pool of exactly 1 is what forces true physical-connection reuse
across tenants, which is the scenario the two guarantees above must survive.

Redis and SQLite enforce the same contract without a database-level
mechanism: every `ApprovalStore` method (`create_pending`, `decide`, `get`,
`list_pending`) takes `tenant` as a required keyword argument, including
single-record lookups by ID — a tenant-scoped system should never have a
"get by ID alone, no tenant" path as a first-class contract method,
regardless of backend. Redis additionally maintains a per-tenant secondary
index (`SADD`/`SMEMBERS`) so listing tenant A's pending approvals never
requires reading tenant B's records at all, even transiently.

### Retrieval isolation

`AuthorizedRetriever.retrieve(query, caller_roles=...)` and the local
`VectorIndex`'s `chunk.allowed_roles <= caller_roles` subset check required
**zero interface changes**. Passing `tenant_context.bundle.entitlements`
instead of the caller's platform roles was sufficient — the leakage suite's
retrieval test passed immediately once tenant bundles existed. This is the
clearest example of "reuse what exists" paying off as designed, not just as
intent.

That reuse surfaced a real vocabulary collision: RAG documents' `allowed_roles`
frontmatter had used platform capability roles (`agent.invoke`,
`privacy.read`) as a stand-in for "any authenticated agent caller," which
coincidentally worked because retrieval had always been scoped by the
caller's platform roles. Switching retrieval to tenant entitlements broke
that coincidence — those documents became permanently unretrievable by any
tenant, since no tenant bundle's `entitlements` will ever contain
`agent.invoke`. Fixed by migrating the pre-existing documents
(`delayed-payments.md`, `refund-approval.md` → `transactions`;
`customer-data.md` → `customer`) to the same entitlement-domain vocabulary
the tenant bundles use, and updating Azure AI Search's
`_KNOWN_CHUNK_ROLES` ingestion-time drift guard (`rag/azure_search.py`) to
match. The specialist-agent policy-search path
(`PolicyTools.search` → `AuthorizedRetriever`, reached from
`/workflows/investigate` via `OperationsWorkflow`) still needs the caller's
platform role for its MCP tool-invocation gate *and* now needs the tenant's
entitlements for document filtering — both checks are subset tests against
one `caller_roles` set, so the gateway unions `principal.roles |
tenant_context.bundle.entitlements` when constructing that call's roles
(`gateway/app.py`), which satisfies both without weakening either. This is
plumbing at the orchestration/gateway boundary, not a change to any
specialist agent's own decision logic.

### Quota isolation

`TenantBudgetPolicy` moved from a single `daily_ceiling_gbp` to a
`ceilings: dict[tenant, gbp]` plus an optional `default_ceiling_gbp`
fallback, populated from each tenant bundle's `token_budget_gbp`
(`model_gateway/factory.py`). A tenant with no bundle and no default ceiling
fails closed with `ModelBudgetExceeded`, not silent unlimited spend.

### Metrics and traces

Every metric that can be attributed to a specific request now carries a
`tenant` label: `MODEL_TOKENS`, `MODEL_ESTIMATED_COST_GBP`,
`MODEL_GATEWAY_CALLS`, `MODEL_GATEWAY_DURATION`, `WORKFLOW_COMPLETIONS`,
`WORKFLOW_DURATION`, `PENDING_APPROVALS`. `observability/grafana/dashboards/
tenants.json` breaks all of these down by tenant.

## Consequences

- A tenant can prove, in CI, that it cannot read another tenant's approval
  state, retrieve another tenant's documents (even when the top semantic
  match), exhaust another tenant's budget, see another tenant's metrics, or
  invoke a skill scoped to another tenant — the six things the design was
  required to prove, not just the easy ones.
- Onboarding a tenant is genuinely a config-only change, mechanically
  enforced by CI, not just true by convention today.
- Local/test-only tenant resolution is an explicit, gated limitation, not a
  silent gap — it fails closed (503) outside `local`/`test`.

## What was deliberately not isolated, and why

- **`SupervisorWorkflow`'s routing-preview metric** (`POST
  /workflows/route`, `orchestration/supervisor.py:_classify`). This path is
  a free, deterministic classification step that precedes tenant resolution
  and does not carry tenant context. Its `MODEL_TOKENS`/
  `MODEL_ESTIMATED_COST_GBP` calls are labelled `"unscoped"` rather than a
  real tenant name, so it stays visibly distinct from actual per-tenant
  spend in dashboards and alerts. Threading tenant context into
  `SupervisorWorkflow`'s graph state would mean touching agent-internal
  orchestration state for a routing preview that spends nothing and
  attributes to no tenant budget — out of proportion to what it buys, and
  explicitly the kind of expansion into agent internals this work's
  instructions said to stop and flag rather than do silently.
- **`HTTP_REQUESTS`, `RAG_RETRIEVALS`, `MCP_CALLS`** remain unlabelled by
  tenant. They are route/tool/outcome-level operational metrics (is the
  gateway itself healthy), not spend-attribution metrics; adding a tenant
  label to genuinely unbounded-cardinality-adjacent series was judged not
  worth the cardinality cost for what they are used for today. This is a
  narrower claim than "everything is tenant-labelled" and is stated as such
  here rather than left to be discovered as a gap.
- **Real JWT-verified tenant claims.** Tenant resolution is local-identity
  trust, the same limitation as caller identity generally
  (`docs/portfolio/limitations.md`). Pre-production gate, not a technical
  blocker specific to tenancy.
- **Durable, cross-replica budget ledgers.** `TenantBudgetPolicy` is
  in-process, same limitation already recorded for the model gateway
  (ADR-006) before this work; multi-tenancy inherits it rather than fixing
  it.

## Alternatives considered

- **Schema-per-tenant** instead of RLS. Rejected for this tenant-count
  regime: it would have meant per-tenant migrations and connection routing
  multiplying with tenant count, for an isolation guarantee RLS already
  provides at the row level without that operational multiplier.
- **A real JWT tenant claim now**, instead of the local-header mechanism.
  Rejected: this codebase has no JWT validation infrastructure at all yet;
  building a partial one to back a single claim would be less honest than
  an explicitly-scoped local mechanism with the same trust boundary as the
  rest of local auth, gated the same way.
- **Threading tenant context into the specialist agents' own state**
  instead of unioning roles at the gateway boundary for the policy-search
  case. Rejected as disproportionate scope expansion into agent-internal
  logic for what a role union already solves correctly at the boundary.

## Verification

`tests/test_tenancy_leakage.py` — six tests, one per required property, all
against the real three-tenant registry loaded from `config/tenants/`, run
before any implementation existed and confirmed failing for genuine reasons
(not a collection error) before being made to pass.
`tests/integration/test_postgres_rls_pool.py` — real Postgres via Docker,
pool size 1, an explicit non-superuser table-owner role; caught a real RLS
bypass during development (see State isolation above) before being fixed.
`scripts/check-tenant-drift.sh` — wired into `make check` and CI; verified
to fail on an injected literal tenant-name reference in `src/`, and to pass
clean. A fourth tenant (`fraud-alerts`) was added as a single YAML file with
zero `src/` diff and confirmed working end-to-end over real HTTP requests
against the running gateway: correctly scoped skill list, successful
tenant-scoped investigation, and automatic appearance in the browser demo's
tenant selector — all without a code change, which is the actual claim this
ADR makes, verified directly rather than inferred from the design.
