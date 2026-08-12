# ADR-005: Authenticated remote MCP

Status: accepted for local reference use. Remote MCP uses stateless Streamable
HTTP, asymmetric RS256 access tokens, strict issuer/audience/time validation and
separate domain scopes. The service receives only a public verification key and
binds to loopback locally. A deployment must replace the local issuer with managed
workload identity and TLS while preserving the same deny-by-default contract.
