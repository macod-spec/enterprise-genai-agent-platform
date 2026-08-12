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
argument fingerprint, outcome, duration and attempts—not raw arguments.

### 5:00–7:00 — demonstrate measurable quality and reliability

Use `.security-reports/evaluation.json` to show independent routing, grounding,
safety and security scores. Use `.security-reports/load-failure.json` to show a
versioned regression threshold and bounded injected failures. State explicitly that
local throughput is not a production capacity result.

### 7:00–9:00 — demonstrate secure delivery and operations

Walk through the `security` Make target and GitHub Actions: test, SAST, secrets,
dependency and licence checks, IaC scan, container scan, SBOM, offline signature,
kind and Helm. Then reference burn-rate alerts, incident runbook and recovery drill.

### 9:00–10:00 — explain cloud posture and trade-offs

“Azure integration is intentionally gated. Terraform defaults to zero resources,
CI has no login or apply, and the local interfaces map to Entra, APIM, private AKS,
AI Search, managed state and Azure Monitor. Before production I would require cost
review, privacy/model-risk approval, external penetration testing, workload identity,
private networking and a measured DR/SLO exercise.”

## Likely questions

- **Why LangGraph?** It makes routing, termination and human-review transitions
  explicit and testable rather than hiding control flow in prompts.
- **Why MCP?** It separates agent reasoning from typed enterprise-tool access and
  provides one place for policy, identity, validation, resilience and audit.
- **How is prompt injection handled?** Ingestion rejects instruction-like content,
  retrieval is role-filtered, retrieved text is evidence rather than executable
  instruction, and tools remain independently authorised.
- **How would Azure change this?** Implementations change behind stable interfaces;
  control objectives and release gates remain.
- **What is not production-ready?** Real identity, managed secrets/private network,
  non-deterministic model evaluation, production capacity/SLO data, organisational
  approvals and external penetration testing.
