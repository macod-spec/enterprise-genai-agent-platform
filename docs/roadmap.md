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
- Current critical path: groundedness evaluation and real hybrid RAG with
  entitlement filtering against Azure AI Search.
- Completed with explicit approval: published the sanitized repository, enabled
  GitHub-hosted CodeQL/code scanning and restored protected `main` branch controls.
- Completed locally: AKS connected-apply preflight blocks Free Trial quota,
  active spending limits, missing compute quota, restricted node SKUs and B-series
  system pools before Terraform can apply.
- Deferred external dependency: the upgraded subscription must stop reporting
  Free Trial quota/spending-limit state and expose regional VM-family quota before
  retrying AKS. Until then, Argo CD, Kyverno and workload identity are demonstrated
  on `kind`; AKS Terraform remains validated and ready.
- In progress: the partially created Azure sandbox is billable and is not yet
  application-ready.
- Pre-production: Entra identity, durable PostgreSQL/Redis state, remote MCP auth,
  managed secrets, load/failure tests and external penetration test.
- Production readiness: DR exercise, SLO baselines, on-call ownership, privacy and
  model-risk approvals, signed provenance and controlled canary deployment.
