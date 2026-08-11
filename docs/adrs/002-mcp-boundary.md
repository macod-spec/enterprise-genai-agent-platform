# ADR-002: Governed MCP boundary

Status: accepted. Specialists access data only through registered MCP contracts.
The gateway supplies identity, policy, validation, rate limits, retries and audit.
ADR-005 defines the authenticated remote transport; local stdio remains available
for isolated development.
