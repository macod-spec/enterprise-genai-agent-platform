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
- Current critical path: Phase 2 model gateway, token/cost and GenAI OpenTelemetry
  telemetry, self-hosted Langfuse, Presidio/Content Safety, groundedness evaluation,
  and real hybrid RAG with entitlement filtering against Azure AI Search.
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
