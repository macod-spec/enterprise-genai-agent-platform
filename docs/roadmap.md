# Platform roadmap

- Completed locally: secure reference platform, validate-only delivery assets,
  hash-bearing dependency lock, Semgrep and license gates, container SBOM and
  high/critical vulnerability gate, offline signature verification and ephemeral
  `kind` integration testing without a registry push, plus authenticated durable
  PostgreSQL/Redis adapters with disposable integration testing, authenticated
  remote MCP transport, and bounded load/failure testing.
- Completed locally: architecture decisions, ownership matrix, privacy/model-risk
  gate, multi-window SLO alerts and executable recovery/evidence exercises.
- Completed locally: expanded routing, grounding, safety and security evaluation
  datasets, enforced category-level quality gates, repeatable performance regression
  baselines and a sanitised secure operator demonstration.
- Completed locally: role-mapped portfolio evidence, logical/security/delivery
  diagrams, explicit limitations and a repeatable ten-minute interview/operator
  demonstration with an automated evidence-completeness gate.
- Completed locally: Azure sandbox cost-driver review, credential-free conditional
  data lookup and an automated Terraform gate proving the default disabled plan
  contains zero resource changes.
- Completed locally: schema-validated private modules for AKS/workload identity,
  PostgreSQL/Redis, AI Search/Azure OpenAI, monitoring/budgets and private endpoints/
  DNS. All module calls remain behind the zero-resource deployment lock.
- Completed locally: OIDC-only remote-state contract, private identity/network
  design, connected-plan/deployment rules and executable pre-production readiness
  audit. Public retail-price research is documented; a subscription quote remains.
- External approval boundary: obtain a subscription-specific calculator export and
  organisational identity/network approvals before any provider-connected non-zero
  plan. External testing and formal privacy/model-risk approval also remain outside
  the local repository.
- Completed with explicit approval: registered Azure providers, created the Entra
  administrator group and secured remote-state prerequisites, generated a clean
  connected plan, and began the platform apply. Networking, ACR, Key Vault,
  PostgreSQL, AI services, monitoring, identity/RBAC and private endpoints exist.
- Completed locally: guarded teardown, environment-age alerts and an explicit
  always-on/development/demo-week resource lifetime policy. Full Git history passes
  Gitleaks and detect-secrets; real subscription, tenant and state-account
  identifiers have been removed from the publishable working tree.
- Completed locally: Phase 2 owned model gateway (ADR-006) — provider-neutral
  contract, deny-by-default model allowlist, per-tenant GBP budget enforcement,
  a zero-cost mock adapter and a keyless Azure OpenAI adapter, GenAI OpenTelemetry
  spans and Prometheus token/cost/latency telemetry, exposed via the gateway API
  and covered by unit/HTTP tests. The Azure OpenAI adapter remains unverified
  against a live deployment pending Azure OpenAI access/quota.
- Completed locally: self-hosted Langfuse (ADR-007) as an optional `langfuse`
  Compose profile (web/worker, its own Postgres/ClickHouse/MinIO/Redis), fed by
  the existing otel-collector via a new `otlphttp/langfuse` fan-out exporter with
  no application code changes. Locally validated end-to-end: a live model-gateway
  call was confirmed ingested and auto-classified as a Langfuse `GENERATION` via
  the public API. Fixed two real bugs found along the way (ClickHouse single-node
  migration config; a root-owned Docker volume that crash-looped the gateway).
  Also validated: local container build → SBOM → HIGH/CRITICAL vuln gate → offline
  cosign signing → ephemeral `kind`/Helm deploy with Kubernetes security
  assertions, end to end, after the model gateway changes.
- Completed locally: Presidio-backed PII detection and masking (ADR-009),
  enforced inside `ModelGateway.generate()` for both request messages and
  provider responses, on by default. `presidio-analyzer` runs against the
  small `en_core_web_sm` spaCy model plus a custom `UK_SORT_CODE` recognizer;
  `presidio-anonymizer` was deliberately left out of the dependency tree
  because it unconditionally pins a `cryptography` range carrying three known
  CVEs, and masking a `presidio-analyzer` result is a ~15-line span
  substitution. Audit metadata (Prometheus counter, HTTP error detail) carries
  entity type and action only, never matched text. Covered by 14 new unit/HTTP
  tests; `make audit`/`sast`/`secrets`/`licenses` all re-verified clean after
  the dependency changes (three additional permissive-license entries needed
  allowlisting: ISC, and two composite BSD/Apache expressions from numpy and
  regex).
- Completed locally: Azure Content Safety guard (ADR-010), structurally
  parallel to the PII guard and enforced in the same place — every request
  message and provider response is checked against a per-category severity
  threshold (Hate/SelfHarm/Sexual/Violence). A free deterministic mock
  provider keeps the policy path exercised without a live Azure resource; a
  keyless `AzureContentSafetyProvider` (via `DefaultAzureCredential`) is
  implemented but not yet verified against a live endpoint, same status as
  the Azure OpenAI adapter. Deliberately fails closed on provider error or a
  missing severity value, an explicit asymmetry with Langfuse's
  don't-fail-inference rule: a safety control going down should not silently
  downgrade to ungoverned. 12 new tests; full container rebuild, vulnerability
  scan, offline signing and `kind`/Helm redeploy re-validated after adding the
  `azure-ai-contentsafety` dependency, plus a direct container smoke test that
  sent both a safe and an unsafe request through the real HTTP endpoint and
  confirmed the block.
- Completed locally: Azure AI Search hybrid retrieval with server-side
  entitlement filtering (ADR-011). `AzureSearchIndex` implements the same
  `VectorIndex` protocol as the local in-memory index, so `AuthorizedRetriever`
  is unchanged by which backend sits behind it; entitlement is enforced as a
  server-side OData `$filter` built from the caller's authenticated roles
  (`allowed_roles/all(r: search.in(...))`, matching the local index's subset
  semantics) and fails closed on an empty role set or a role containing the
  filter delimiter — no code path accepts a client-supplied filter. Hybrid
  combines Azure BM25 keyword search with vector search over the platform's
  existing free local embedding; a live embedding model is deferred to Azure
  OpenAI validation. Index management (`scripts/ingest_azure_search.py`) is
  intentionally separate from the serving path. `VectorIndex.search` and
  `AuthorizedRetriever.retrieve` became `async` to support a real network
  backend; the one production caller and all local-index tests were updated.
  22 new/updated tests; full container rebuild, vulnerability scan, signing
  and `kind`/Helm redeploy re-validated, plus a direct container smoke test
  of the async local retrieval path end-to-end. A real circular-import bug
  was found and fixed along the way (an unused eager re-export in
  `gateway/__init__.py`). `AzureSearchIndex` and the ingestion script are
  implemented and type-checked but not yet exercised against a live Azure AI
  Search resource, same status as the other Azure adapters.
- Completed locally: groundedness evaluation for synthesized RAG answers
  (ADR-012), additive to the existing routing/evidence flow rather than a
  change to it. `rag/synthesis.py` builds a cited-answer prompt from
  authorized evidence only and calls the owned model gateway (so allowlist,
  budget, PII and content-safety controls all apply to it automatically);
  `rag/groundedness.py` is a deterministic, rule-based scorer (term overlap,
  citations found, fabricated citations, composite pass/fail) reproducible in
  CI without a live model. Exposed via `POST /api/v1/rag/answer`. A real
  scoring bug was found and fixed while writing the evaluator's own test
  cases: citation brackets were being tokenized into the term-overlap
  calculation, penalizing every properly-cited answer. Because the mock
  model's output is a generic acknowledgement rather than a real answer,
  grading it against a "must be grounded" bar would be meaningless — the new
  CI-integrated quality gate (`make groundedness-evaluation`) instead proves
  the evaluator correctly classifies four known cases and separately records
  the honest (ungrounded) mock-pipeline result as evidence. 25 new tests;
  full container rebuild, vulnerability scan, signing and `kind`/Helm
  redeploy re-validated, plus a direct container smoke test of the live
  endpoint. This closes out the Phase 2 GenAI application layer (model
  gateway, telemetry, Langfuse, PII, content safety, hybrid RAG, groundedness
  — ADR-006 through ADR-012).
- Completed locally: GitHub Actions delivery pipeline as code (ADR-013) — four
  new `workflow_dispatch`-only workflows filling the gap `ci.yaml` deliberately
  leaves open (it builds/scans/plans-zero on every push/PR but never logs into
  Azure, pushes, applies or deploys). `container-publish.yaml` builds, SBOMs,
  vulnerability-gates, then — behind a protected `container-registry`
  Environment — pushes to ACR and keyless-signs the digest with cosign (OIDC
  identity, public Rekor log), distinct from local `kind` validation's
  ephemeral-key blob signing. `terraform-plan.yaml` produces a real, reviewable
  plan against remote state without ever applying. `terraform-apply.yaml`
  splits plan and apply into separate jobs so a protected-Environment approval
  is against the exact plan file reviewed, not a fresh re-plan. `deploy.yaml`
  Helm-deploys a digest-pinned image to AKS (rejects floating tags outright)
  with a real health-check smoke test and automatic rollback on failure. Every
  state-changing job carries both a typed confirmation input and a protected-
  Environment approval gate. All four authenticate via Azure OIDC federation
  (`azure/login@v2`, no stored client secret) and are `actionlint`-clean across
  all seven repository workflows.
  **Deliberately not run and not yet live**: the one-time Azure AD app
  registration, federated credentials, role assignments and GitHub
  secrets/variables these workflows need are documented with exact commands in
  `docs/ci-cd-azure-setup.md`, but none were executed — granting an automated
  identity permission to act on the real subscription is a credentials/cloud-
  permissions decision for the platform owner. `deploy.yaml` will additionally
  fail cleanly at `az aks get-credentials` until AKS itself exists.
- Completed with explicit approval: published the sanitized repository, enabled
  GitHub-hosted CodeQL/code scanning and restored protected `main` branch controls.
- Completed locally: AKS connected-apply preflight blocks Free Trial quota,
  active spending limits, missing compute quota, restricted node SKUs and B-series
  system pools before Terraform can apply.
- Deferred external dependency: the upgraded subscription must stop reporting
  Free Trial quota/spending-limit state and expose regional VM-family quota before
  retrying AKS. Until then, Argo CD, Kyverno and workload identity are demonstrated
  on `kind`; AKS Terraform remains validated and ready.
- Completed with explicit approval: Azure OIDC federation for the CD pipeline
  (`docs/ci-cd-azure-setup.md`) — app registration, five federated credentials,
  `AcrPush`/`Storage Blob Data Contributor`/`Contributor` role assignments,
  GitHub secrets/variables and four protected Environments. `terraform-plan.yaml`
  has run live end-to-end: real OIDC login, real `terraform init` against remote
  state, and a real connected plan (5 to add, 2 to change, 0 to destroy — AKS,
  managed Redis, workload identity federation, ACR-pull role assignment), proving
  the CD pipeline authored in ADR-013 actually works, not just that it lints
  clean. Two real bugs were found only by running it live: GitHub's OIDC subject
  claim uses an undocumented "immutable ID" format keyed by numeric owner/repo
  IDs rather than names (the first run failed `AADSTS700213`); and the Terraform
  state storage account's single-IP firewall unconditionally blocks GitHub-hosted
  runners, whose 7,280 published CIDR ranges exceed Azure's 200-rule-per-account
  IP allowlist cap — resolved, with explicit approval, by opening the storage
  account's network layer while keeping `allowSharedKeyAccess=false`, so Azure AD
  auth remains the only way in. Re-checked the AKS quota block at the same time
  (`scripts/azure-aks-preflight.sh`): the subscription reports zero compute
  quota entries in every region checked, not just uksouth — Azure's Support
  Tickets API refused to file an increase request ("Free" support plan not
  eligible even for quota-only requests via API), so that step now needs the
  Azure Portal directly. `container-publish.yaml` and `terraform-apply.yaml`
  are identity- and RBAC-ready but not yet dispatched; `deploy.yaml` still
  cannot be proven live until AKS exists.
- In progress: the partially created Azure sandbox is billable and is not yet
  application-ready.
- Pre-production: Entra identity, durable PostgreSQL/Redis state, remote MCP auth,
  managed secrets, load/failure tests and external penetration test.
- Production readiness: DR exercise, SLO baselines, on-call ownership, privacy and
  model-risk approvals, signed provenance and controlled canary deployment.
