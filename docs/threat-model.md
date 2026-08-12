# Threat model

## Protected assets

Caller identity, tool authority, synthetic confidential records, policy corpus,
workflow state, audit integrity, model configuration and software artifacts.

## Principal threats and controls

| Threat | Control |
|---|---|
| Spoofed caller | Local headers rejected outside local/test; production identity fails closed |
| Forged remote MCP token | RS256-only verification, issuer/audience/time checks, domain scopes |
| MCP network rebinding | Loopback binding and SDK host/origin transport protections |
| Excessive agency | Read-only tools, explicit allowlists, bounded graph, human approval |
| Cross-agent confused deputy | Caller and agent context propagated; per-agent MCP policy |
| Prompt injection | Strict corpus ingestion, no instruction execution, golden attack cases |
| RAG data disclosure | Role metadata filtered before vector ranking |
| Tool argument abuse | Pydantic schemas, unknown-field rejection, timeouts and rate limits |
| Sensitive telemetry | Redaction, hashed query/argument fingerprints, no request-body logging |
| Supply-chain compromise | SCA, SAST, image/IaC scans, SBOM and offline signing gate |
| Cloud cost accident | Terraform count zero, double confirmation, no apply workflow |

Residual risks include local-header trust in development, in-memory MCP audit
retention, deterministic embeddings with limited semantic quality, a local JWT
issuer that is demonstration-only, and Azure controls not yet exercised against
a real tenant. Privacy and model-risk approval remains explicitly outstanding.
