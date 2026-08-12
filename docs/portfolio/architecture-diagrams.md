# Architecture diagrams

## Logical platform

```mermaid
flowchart TB
    Team[Developer team / Backstage template / Python SDK] --> Edge[FastAPI agent gateway]
    Edge --> Auth[Local identity and RBAC\nEntra integration boundary]
    Auth --> Graph[Bounded LangGraph supervisor]
    Graph --> Customer[Customer specialist]
    Graph --> Payments[Payments specialist]
    Graph --> Policy[Policy specialist]
    Graph --> Review[Human review]
    Customer --> MCP[Governed MCP gateway]
    Payments --> MCP
    Policy --> MCP
    MCP --> Records[Synthetic NovaBank records]
    MCP --> RAG[Authorised local RAG]
    RAG --> Corpus[Versioned synthetic policies]
    Review --> State[(SQLite local / PostgreSQL or Redis adapters)]
    Edge --> Telemetry[OpenTelemetry / Prometheus]
    MCP --> Audit[Metadata-only audit]
```

Trust boundaries are explicit: public requests terminate at the gateway; agents
cannot access records directly; each MCP invocation validates identity, role,
agent allowlist, schema, rate, timeout and output; high-risk or unknown work ends
at human review.

## Secure request sequence

```mermaid
sequenceDiagram
    actor User as Authenticated caller
    participant API as Gateway
    participant LG as LangGraph supervisor
    participant Agent as Approved specialist
    participant MCP as Governed MCP boundary
    participant Data as Synthetic data / RAG
    participant Approval as Approval store

    User->>API: Query + identity + request ID
    API->>API: Authenticate, authorise, rate/body/timeout controls
    API->>LG: Bounded workflow invocation
    LG->>LG: Classify to allowlisted route
    alt Read-only approved capability
        LG->>Agent: Query + caller context
        Agent->>MCP: Typed tool request
        MCP->>MCP: Agent/RBAC/schema/rate/timeout checks
        MCP->>Data: Read-only lookup
        Data-->>MCP: Typed result
        MCP-->>Agent: Validated output + metadata audit
        Agent-->>User: Evidence with source IDs
    else Consequential, unknown, mismatched or failed
        LG->>Approval: Store pending record with query SHA-256 only
        LG-->>User: Human review required; no action executed
    end
```

## Delivery and security gates

```mermaid
flowchart LR
    Change[Local change / pull request] --> Quality[Format + lint + typing + tests]
    Quality --> AI[AI evaluation\nrouting / grounding / safety / security]
    AI --> AppSec[Secrets + SAST + dependency + licence gates]
    AppSec --> Build[Hardened multi-stage image build]
    Build --> Supply[SBOM + HIGH/CRITICAL scan + offline signature]
    Supply --> Kind[Ephemeral kind + Helm security assertions]
    Kind --> Evidence[Local security reports]
    Plan[Terraform fmt/validate/plan contract] --> Evidence
    Evidence -. explicit approval required .-> Cloud[Future Azure deployment]
```

The dotted final edge is deliberately inactive. CI contains no cloud login,
Terraform apply, registry push or deployment step.

## Azure target mapping, not deployment evidence

| Local interface | Future managed implementation |
| --- | --- |
| Local headers and RBAC | Microsoft Entra ID and APIM policies |
| Docker and kind/Helm | ACR and private AKS |
| Local deterministic model | Azure OpenAI / Microsoft Foundry |
| Local RAG index | Azure AI Search |
| PostgreSQL/Redis adapters | Managed PostgreSQL and Azure Managed Redis |
| OpenTelemetry/Prometheus | Azure Monitor/Application Insights plus managed metrics |
| Local signature exercise | Workload-identity keyless signing and provenance |
