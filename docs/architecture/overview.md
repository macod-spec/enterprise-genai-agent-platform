# Architecture overview

The platform exposes a secure FastAPI edge, a bounded LangGraph supervisor,
governed specialist agents, an allowlisted MCP tool boundary, authorized RAG with
grounded-answer synthesis and groundedness scoring, an owned model gateway with
PII and content-safety enforcement, versioned skills, pluggable durable approval
state, offline evaluation and optional OpenTelemetry/Langfuse export.

```text
Caller → Gateway/RBAC → LangGraph supervisor → approved specialist
                                      ├── governed MCP → synthetic records
                                      └── policy MCP → authorized RAG (local index
                                                        or Azure AI Search adapter)
                                                        → synthesis → groundedness
All model calls (routing or RAG synthesis) → owned model gateway
                                      → allowlist/budget → PII guard
                                      → content-safety guard → provider
                                      (mock, or keyless Azure OpenAI adapter)
All paths → request correlation, audit, evaluation, approval and telemetry
```

```text
Local/test state: SQLite
Durable state:    Gateway → authenticated PostgreSQL (system of record)
                         └→ authenticated Redis (rebuildable state/cache)

Remote MCP: Agent → loopback/TLS boundary → RS256 JWT validation
                                      └→ domain scope → approved MCP tools
```

Local substitutes implement stable interfaces. PostgreSQL, Redis, authenticated
remote MCP, and self-hosted Langfuse observability now run locally. Keyless
adapters for Azure OpenAI, Azure AI Search and Azure Content Safety are
implemented behind those same interfaces but unverified against a live Azure
endpoint; Entra ID, APIM, AKS, Key Vault, managed PostgreSQL/Redis, Foundry,
Azure Monitor and managed identities remain future integrations. A full
`workflow_dispatch`-only CD pipeline (publish/plan/apply/deploy, ADR-013) exists
as validated code but has not authenticated to Azure. Terraform creation is
disabled by default.
