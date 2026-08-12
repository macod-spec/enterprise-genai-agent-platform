# Role evidence matrix

| Capability | Implemented evidence | Verification | Honest boundary |
| --- | --- | --- | --- |
| Agent platform | FastAPI gateway, LangGraph supervisor and three specialists | `tests/test_gateway.py`, `tests/test_operations_workflow.py` | Deterministic local model |
| Supervisors and workflows | Bounded conditional graph and human-review route | `tests/test_supervisor.py` | No autonomous write action |
| MCP and tools | Typed, allowlisted, authenticated local and remote MCP boundary | `tests/test_mcp_boundary.py` | Remote reference uses local keys, not Entra workload identity |
| Model gateway | Deny-by-default allowlist, per-tenant GBP budget, GenAI OTel spans, token/cost metrics, keyless Azure OpenAI adapter (ADR-006) | `tests/test_model_gateway.py` | Azure OpenAI adapter implemented, not exercised against a live endpoint |
| LLM observability | Self-hosted Langfuse fed via an otel-collector fan-out exporter; verified end-to-end ingestion in this session (ADR-007) | `docs/adrs/007-langfuse-observability.md` | Demo-week-only Compose profile, not always-on |
| PII protection | Presidio-backed detection and masking on every model-gateway call, on by default (ADR-009) | `tests/test_pii.py` | `en_core_web_sm` accuracy trade-off vs the larger default model |
| Content safety | Category/severity guard structurally parallel to PII, fails closed on provider error (ADR-010) | `tests/test_content_safety.py` | Azure Content Safety adapter implemented, not exercised live |
| RAG | Versioned ingestion, injection rejection, role-filtered retrieval and citations; server-side entitlement-filtered Azure AI Search hybrid adapter behind the same interface (ADR-011) | `tests/test_rag.py`, `tests/test_azure_search.py` | Local deterministic vectors by default; Azure AI Search adapter implemented, not exercised live |
| Groundedness evaluation | Deterministic term-overlap and fabricated-citation scoring for synthesized RAG answers, `POST /api/v1/rag/answer` (ADR-012) | `tests/test_groundedness.py`, `make groundedness-evaluation` | Mock model output is honestly ungrounded; scorer correctness is what the gate proves |
| State and memory | SQLite plus authenticated PostgreSQL/Redis approval adapters | `make durable-state-integration` | Approval workflow state, not conversational long-term memory |
| Skills and reuse | Governed skill registry, starter template and Backstage scaffolder | `tests/test_skills.py` | Template evidence; no live Backstage instance |
| APIs and SDK | Authenticated REST API and Python client | `tests/test_gateway.py` | Local identity outside production |
| Containers and Kubernetes | Hardened Dockerfile, Helm security contexts and ephemeral kind | `make kind-integration` | Local cluster only, no AKS claim |
| Infrastructure as code | Cost-locked Azure Terraform with creation disabled by default | `make terraform-zero-plan` proves zero changes | No Azure apply or provisioned resource |
| Observability and SLOs | OpenTelemetry, bounded metrics, dashboard and burn-rate alerts | `tests/test_metrics.py`, Prometheus rule validation | Proposed SLO until production traffic exists |
| AI quality | Twelve versioned routing, grounding, safety and security cases | `make evaluate` | Synthetic deterministic dataset |
| Reliability and latency | Retries, timeouts, fail-closed errors and median regression baseline | `make reliability` | Local throughput is not production capacity |
| Governance | Human approval, ownership, privacy/model-risk gates and ADRs | `make operational-readiness` | Formal organisational approvals still required |
| Security | RBAC, minimisation, threat model, secrets/SAST/SCA/IaC/container/SBOM/signing gates | `make security`, `make sign-image` | External penetration test remains pre-production work |
| Delivery | Non-deploying GitHub Actions and signed local artifact contract, plus a publish/plan/apply/deploy pipeline (ADR-013) with live-verified Azure OIDC federation | `.github/workflows/ci.yaml`, `.github/workflows/container-publish.yaml`, `.github/workflows/terraform-plan.yaml`, `.github/workflows/terraform-apply.yaml`, `.github/workflows/deploy.yaml`, `docs/ci-cd-azure-setup.md` | `terraform-plan.yaml` has run live end-to-end against real remote state; `container-publish.yaml`/`terraform-apply.yaml` are identity-ready but not yet dispatched; `deploy.yaml` needs AKS, still quota-blocked |
| Operations | Runbook, recovery exercise, SLOs, incident roles and evidence reports | `make operational-readiness` | Local recovery proves mechanics, not production RPO/RTO |

Generated, sanitised evidence is stored under ignored `.security-reports/` so
scanner output and machine-specific results are not accidentally committed.
