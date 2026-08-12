# Security engineering approach

## Core principles

1. Local-first development: validation never provisions cloud resources.
2. Least privilege: identities, agents, MCP tools, workloads, and pipelines receive
   only the permissions they require.
3. Deny by default: tools, network destinations, retrieved documents, and deployment
   actions require explicit authorization.
4. Traceable decisions: security-relevant agent and tool actions produce redacted,
   correlated audit events.
5. Shift-left controls: inexpensive checks run before commit; deeper checks run before
   a release can progress.

## Control layers

| Layer | Planned controls and tools |
|---|---|
| Workstation | pre-commit, Ruff, mypy, Bandit, detect-secrets, local Semgrep rules |
| Python dependencies | hash-bearing uv lock, frozen CI sync, pip-audit, license policy |
| Application | authentication, authorization, validation, rate limits, secure headers |
| AI agents | prompt-injection tests, tool allowlists, output validation, data redaction |
| MCP | schema validation, scoped credentials, timeouts, audit logs, deny-by-default tools |
| RAG | document ACLs, metadata filters, provenance, citation checks, content isolation |
| Containers | Hadolint, non-root runtime, read-only filesystem, Trivy, Syft/Grype SBOM scan |
| Kubernetes | security contexts, network policies, resource limits, kube-linter, Checkov |
| Terraform | fmt/validate, TFLint, Checkov/Trivy IaC; no automatic apply |
| CI/CD | minimal token permissions, immutable artifacts, signed provenance, manual deploy gate |
| Runtime | OpenTelemetry, redacted logs, alerts, audit retention, incident runbooks |

## Local commands and side effects

| Command | Effect | Creates cloud resources? |
|---|---|---|
| `make check` | Lints, type-checks, and tests local files | No |
| `make security` | Adds dependency, source, and secret scans | No |
| `make sign-image` | Builds/scans and locally signs an exported image archive | No |
| `make kind-integration` | Runs and deletes an ephemeral Docker-hosted cluster | No |
| `make durable-state-integration` | Tests authenticated PostgreSQL/Redis and deletes their test volumes | No |
| `make reliability` | Runs concurrent MCP load and injected timeout tests | No |
| `make operational-readiness` | Runs recovery and operational-evidence drills | No |
| `make operator-demo` | Exercises local access, approval and audit controls | No |
| `make terraform-zero-plan` | Proves the disabled Terraform plan has zero changes | No |
| `terraform validate` | Validates local Terraform configuration | No |
| non-zero `terraform plan` | May query Azure; requires separate explicit approval | No resources, but not automatic |
| `terraform apply` | Provisions or changes resources | **Yes—explicit approval required** |

## Finding policy

Findings are fixed where possible. Any exception must document the finding, owner,
rationale, compensating control, review date, and expiry date. High or critical
findings block release unless formally accepted.
