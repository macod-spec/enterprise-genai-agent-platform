# Role evidence matrix

## Verification labels

Every row below carries exactly one label. `scripts/portfolio-evidence.py` fails
the build if any row is missing one.

| Label | Meaning |
| --- | --- |
| `VERIFIED-LIVE` | Executed against a real Azure endpoint. Run/log linked. |
| `VERIFIED-LOCAL` | Executed against a mock, Kind, Compose, or an offline/loopback harness. |
| `UNVERIFIED` | Code exists, types check, unit tests pass — never executed against the real dependency it targets. |

A row's label reflects its weakest claim. Where one capability bundles a
locally-verified core with a not-yet-live Azure adapter, it is split into two
rows so neither claim borrows the other's evidence.

## Matrix

| Capability | Label | Implemented evidence | Verification | Honest boundary |
| --- | --- | --- | --- | --- |
| Agent platform | `VERIFIED-LOCAL` | FastAPI gateway, LangGraph supervisor and three specialists | `tests/test_gateway.py`, `tests/test_operations_workflow.py` | Deterministic local model |
| Supervisors and workflows | `VERIFIED-LOCAL` | Bounded conditional graph and human-review route | `tests/test_supervisor.py` | No autonomous write action |
| MCP and tools (local + remote) | `VERIFIED-LOCAL` | Typed, allowlisted, authenticated MCP boundary; remote transport tested over loopback with RS256 JWT validation | `tests/test_mcp_boundary.py` (`127.0.0.1` loopback `TestClient`, not a deployed network service) | Remote reference uses local keys, not Entra workload identity |
| Model gateway (core) | `VERIFIED-LOCAL` | Deny-by-default allowlist, per-tenant GBP budget, GenAI OTel spans, token/cost metrics, mock adapter (ADR-006) | `tests/test_model_gateway.py`, container HTTP smoke test via `kind`/Helm | Mock provider; no real model output |
| Model gateway — Azure OpenAI adapter | `VERIFIED-LIVE` | Keyless `DefaultAzureCredential` adapter, same contract as the mock (ADR-006) | `tests/integration/test_azure_openai_live.py`, `docs/portfolio/live-verification.md` | Live-verified against a real `gpt-5-nano` deployment; two real bugs found and fixed only by running it live (`max_tokens`, `temperature`) |
| LLM observability | `VERIFIED-LOCAL` | Self-hosted Langfuse fed via an otel-collector fan-out exporter; a real model-gateway call was confirmed ingested and auto-classified as a `GENERATION` via the Langfuse public API (ADR-007) | `docs/adrs/007-langfuse-observability.md` | Demo-week-only Compose profile, not always-on; Langfuse itself is self-hosted, not an Azure service |
| PII protection | `VERIFIED-LOCAL` | Presidio-backed detection and masking on every model-gateway call, on by default (ADR-009) | `tests/test_pii.py` | `en_core_web_sm` accuracy trade-off vs the larger default model |
| Content safety (core guard) | `VERIFIED-LOCAL` | Category/severity guard, fails closed on provider error, mock provider; a running container was sent one safe and one unsafe request over real HTTP and the block was confirmed (ADR-010) | `tests/test_content_safety.py` | The HTTP call was real; the Content Safety *decision* behind it was the mock provider, not Azure — the block proves the guard's wiring, not Azure Content Safety's accuracy |
| Content safety — Azure Content Safety adapter | `UNVERIFIED` | Keyless `AzureContentSafetyProvider` (ADR-010) | Unit/type-checked only | Never called a real Azure Content Safety endpoint |
| RAG (local index) | `VERIFIED-LOCAL` | Versioned ingestion, injection rejection, role-filtered retrieval and citations | `tests/test_rag.py` | Local deterministic vectors, not a real embedding model |
| RAG — Azure AI Search adapter | `UNVERIFIED` | Server-side entitlement-filtered hybrid adapter behind the same `VectorIndex` interface (ADR-011) | `tests/test_azure_search.py` (unit-level, mocked SDK calls) | Never queried a real Azure AI Search index |
| Groundedness evaluation | `VERIFIED-LOCAL` | Deterministic term-overlap and fabricated-citation scoring for synthesized RAG answers, `POST /api/v1/rag/answer` (ADR-012) | `tests/test_groundedness.py`, `make groundedness-evaluation`, container HTTP smoke test | Mock model output is honestly ungrounded; scorer correctness is what the gate proves |
| State and memory | `VERIFIED-LOCAL` | SQLite plus authenticated PostgreSQL/Redis approval adapters | `make durable-state-integration` (disposable containers) | Approval workflow state, not conversational long-term memory |
| Skills and reuse | `UNVERIFIED` | Governed skill registry, starter template and Backstage scaffolder template | `tests/test_skills.py` (registry logic only) | Template evidence; no live Backstage instance exists to verify the scaffolder against |
| APIs and SDK | `VERIFIED-LOCAL` | Authenticated REST API and Python client | `tests/test_gateway.py` | Local identity outside production |
| Containers and Kubernetes | `VERIFIED-LOCAL` | Hardened Dockerfile, Helm security contexts and ephemeral kind | `make kind-integration` | Local cluster only, no AKS claim |
| Infrastructure as code — offline zero-resource plan | `VERIFIED-LOCAL` | Cost-locked Azure Terraform, creation disabled by default, `-backend=false` (no Azure login at all) | `make terraform-zero-plan` proves zero resource changes | Proves the disabled-by-default posture, not that a real apply works |
| Infrastructure as code — connected plan | `VERIFIED-LIVE` | Real `terraform init`/`plan` against real remote state via Azure OIDC federation (ADR-013) | `terraform-plan.yaml` run [31615813368](https://github.com/macod-spec/enterprise-genai-agent-platform/actions/runs/31615813368) — real plan, 5 to add / 0 to change / 0 to destroy after the budget-email fix | Plan only; nothing has been applied |
| Infrastructure as code — apply / AKS | `UNVERIFIED` | `terraform-apply.yaml`, `deploy.yaml` (ADR-013); AKS module validated; live preflight now passes with `Standard_D2ns_v6` | Identity- and RBAC-ready, never dispatched | No longer quota-blocked (`docs/azure-diagnosis.md`); a real apply is a genuine ongoing cost held for explicit sign-off, not a technical blocker |
| Observability and SLOs | `VERIFIED-LOCAL` | OpenTelemetry, bounded metrics, dashboard and burn-rate alerts | `tests/test_metrics.py`, Prometheus rule validation | Proposed SLO until production traffic exists |
| AI quality | `VERIFIED-LOCAL` | Twelve versioned routing, grounding, safety and security cases | `make evaluate` | Synthetic deterministic dataset |
| Reliability and latency | `VERIFIED-LOCAL` | Retries, timeouts, fail-closed errors and median regression baseline | `make reliability` | Local throughput is not production capacity |
| Governance | `VERIFIED-LOCAL` | Human approval, ownership, privacy/model-risk gates and ADRs | `make operational-readiness` | Formal organisational approvals still required — see `docs/governance/` |
| Security | `VERIFIED-LOCAL` | RBAC, minimisation, threat model, secrets/SAST/SCA/IaC/container/SBOM/signing gates | `make security`, `make sign-image` | External penetration test remains pre-production work |
| Delivery — CD pipeline identity | `VERIFIED-LIVE` | Azure OIDC federation: app registration, federated credentials, role assignments, protected Environments (ADR-013) | `docs/ci-cd-azure-setup.md` | Identity works; publish/apply/deploy jobs not yet dispatched |
| Delivery — container publish / apply / deploy | `UNVERIFIED` | `container-publish.yaml`, `terraform-apply.yaml`, `deploy.yaml` | `actionlint`-clean, identity-ready | Never dispatched for real |
| Operations | `VERIFIED-LOCAL` | Runbook, recovery exercise, SLOs, incident roles and evidence reports | `make operational-readiness` | Local recovery proves mechanics, not production RPO/RTO |

Generated, sanitised evidence is stored under ignored `.security-reports/` so
scanner output and machine-specific results are not accidentally committed.
