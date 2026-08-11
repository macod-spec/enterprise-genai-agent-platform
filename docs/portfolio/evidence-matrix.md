# Role evidence matrix

| Capability | Implemented evidence | Verification | Honest boundary |
| --- | --- | --- | --- |
| Agent platform | FastAPI gateway, LangGraph supervisor and three specialists | `tests/test_gateway.py`, `tests/test_operations_workflow.py` | Deterministic local model |
| Supervisors and workflows | Bounded conditional graph and human-review route | `tests/test_supervisor.py` | No autonomous write action |
| MCP and tools | Typed, allowlisted, authenticated local and remote MCP boundary | `tests/test_mcp_boundary.py` | Remote reference uses local keys, not Entra workload identity |
| RAG | Versioned ingestion, injection rejection, role-filtered retrieval and citations | `tests/test_rag.py` | Local deterministic vectors, not Azure AI Search |
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
| Delivery | Non-deploying GitHub Actions and signed local artifact contract | `.github/workflows/ci.yaml` | No cloud credentials, pushes or deployment |
| Operations | Runbook, recovery exercise, SLOs, incident roles and evidence reports | `make operational-readiness` | Local recovery proves mechanics, not production RPO/RTO |

Generated, sanitised evidence is stored under ignored `.security-reports/` so
scanner output and machine-specific results are not accidentally committed.
