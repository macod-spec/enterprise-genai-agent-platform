# Ten-minute interview and operator demo

## Preparation

Run `make portfolio-demo` from the repository root. It executes only deterministic
local checks and produces sanitised JSON evidence. Docker and cloud credentials are
not required.

## Narrative and timing

### 0:00–1:00 — frame the platform problem

“Business teams need agents, but duplicated security, orchestration, RAG, tooling,
delivery and operations create risk. This repository is the paved road: reusable
interfaces and mandatory controls, demonstrated by a fictional banking workload.”

Show `docs/portfolio/architecture-diagrams.md` and point out the gateway, bounded
supervisor, specialist agents, MCP boundary and human-review stop.

### 1:00–3:00 — demonstrate controlled orchestration

Use `.security-reports/operator-demo.json`. Explain that a read-only investigation
returns cited synthetic evidence, while a caller with the wrong role is denied.
The deterministic model keeps the demonstration free, offline and reproducible.

### 3:00–5:00 — demonstrate safety and data minimisation

Show that a refund instruction is not executed. It creates a pending approval with
only the SHA-256 digest of the query. MCP audit evidence similarly stores an
argument fingerprint, outcome, duration and attempts—not raw arguments. Then show
that every model-gateway call — not just MCP tool calls — is independently gated:
a deny-by-default model allowlist, a per-tenant budget, and Presidio-backed PII and
Azure Content Safety checks run on both the outbound request and the model's
response, and fail closed rather than silently letting ungoverned content through.

### 5:00–7:00 — demonstrate measurable quality and reliability

Use `.security-reports/evaluation.json` to show independent routing, grounding,
safety and security scores. Call `POST /api/v1/rag/answer` to show a cited,
synthesized answer plus its deterministic groundedness score (term overlap,
citation correctness, fabricated-citation detection) — `make groundedness-evaluation`
is the CI gate that proves the scorer itself is correct on known cases, since the
free mock model's own answers are honestly ungrounded. Use
`.security-reports/load-failure.json` to show a versioned regression threshold and
bounded injected failures. State explicitly that local throughput is not a
production capacity result.

### 7:00–9:00 — demonstrate secure delivery and operations

Walk through the `security` Make target and GitHub Actions: test, SAST, secrets,
dependency and licence checks, IaC scan, container scan, SBOM, offline signature,
kind and Helm. Then show the four `workflow_dispatch`-only CD workflows
(`container-publish.yaml`, `terraform-plan.yaml`, `terraform-apply.yaml`,
`deploy.yaml`, ADR-013): OIDC login with no stored client secret, keyless cosign
signing to a public Rekor log, a plan/apply job split so approval targets the exact
reviewed plan, and a digest-pinned Helm deploy with automatic rollback. Explain they
are `actionlint`-clean and ready but deliberately not yet authenticated — see below.
Then reference burn-rate alerts, incident runbook and recovery drill.

### 9:00–10:00 — explain cloud posture and trade-offs

“Azure integration is intentionally gated in layers. Terraform defaults to zero
resources and CI never logs in or applies. One layer up, keyless adapters for Azure
OpenAI, Azure AI Search and Azure Content Safety, plus the CD workflows themselves,
are fully implemented and type-checked but not yet exercised against live Azure
endpoints — that requires a one-time Azure identity federation step
(`docs/ci-cd-azure-setup.md`) I've deliberately left as a separate human decision
rather than an implicit side effect of writing YAML. AKS itself remains blocked on
compute quota. Before production I would also require cost review, privacy/model-risk
approval, external penetration testing, private networking and a measured DR/SLO
exercise.”

## Likely questions

- **Why LangGraph?** It makes routing, termination and human-review transitions
  explicit and testable rather than hiding control flow in prompts.
- **Why MCP?** It separates agent reasoning from typed enterprise-tool access and
  provides one place for policy, identity, validation, resilience and audit.
- **How is prompt injection handled?** Ingestion rejects instruction-like content,
  retrieval is role-filtered, retrieved text is evidence rather than executable
  instruction, and tools remain independently authorised.
- **How would Azure change this?** Implementations change behind stable interfaces;
  control objectives and release gates remain. The Azure OpenAI, AI Search and
  Content Safety adapters already exist behind those interfaces — only live
  verification and identity federation are outstanding.
- **Why not just call the model provider directly?** Every generation call goes
  through one owned gateway — allowlist, budget, PII and content-safety checks are
  enforced there once, not re-implemented per caller, and nothing bypasses it.
- **Why is groundedness graded on the mock model's honestly ungrounded output
  instead of a "passing" answer?** Faking a grounded answer from a deterministic
  mock would be evidence theft. The gate instead proves the scorer is correct on
  known cases and records the mock result as an honest baseline.
- **Why author CD workflows you haven't run?** Writing and validating
  (`actionlint`) the pipeline is separable from granting an automated identity
  permission to act on a real subscription — the second is a deliberate,
  separately-approved decision, not a default.
- **What is not production-ready?** Real identity, managed secrets/private network,
  non-deterministic model evaluation, production capacity/SLO data, live-verified
  Azure adapters, an authenticated CD pipeline, organisational approvals and
  external penetration testing.
