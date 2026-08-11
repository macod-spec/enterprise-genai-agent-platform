# Architecture overview

The platform exposes a secure FastAPI edge, a bounded LangGraph supervisor,
governed specialist agents, an allowlisted MCP tool boundary, authorized RAG,
versioned skills, pluggable durable approval state, offline evaluation and
optional OpenTelemetry export.

```text
Caller → Gateway/RBAC → LangGraph supervisor → approved specialist
                                      ├── governed MCP → synthetic records
                                      └── policy MCP → authorized local RAG
All paths → request correlation, audit, evaluation, approval and telemetry
```

```text
Local/test state: SQLite
Durable state:    Gateway → authenticated PostgreSQL (system of record)
                         └→ authenticated Redis (rebuildable state/cache)

Remote MCP: Agent → loopback/TLS boundary → RS256 JWT validation
                                      └→ domain scope → approved MCP tools
```

Local substitutes implement stable interfaces. PostgreSQL, Redis and authenticated
remote MCP adapters now run locally. Azure services remain future integrations:
Entra ID, APIM, AKS, Key Vault, managed PostgreSQL/Redis, AI Search, Foundry,
Azure Monitor and managed identities. Terraform creation is disabled by default.
