# ADR-007: Use Langfuse for LLM observability and evaluation

Status: accepted

## Context

Standard OpenTelemetry covers service health, but operators also need prompt and
trace inspection, token and cost analysis, datasets, experiments and evaluation
results. The platform must self-host this capability and keep sensitive payload
capture disabled or redacted by default.

## Decision

Use self-hosted Langfuse as the Phase 2 LLM operations layer, fed from the gateway
and agent through its OpenTelemetry-compatible tracing integration. Azure Monitor
remains the infrastructure and service telemetry backend. Langfuse is an optional
Compose profile locally and a demo-week-only workload in managed environments.

Prompt and response bodies are not collected by default. Trace metadata uses
pseudonymous tenant/request identifiers, and retention and access controls are
environment-specific.

## Consequences

- One UI connects traces, model usage, costs, datasets and evaluation evidence.
- OTel-based instrumentation reduces lock-in and keeps operational metrics in the
  existing Azure Monitor path.
- Self-hosting introduces PostgreSQL, upgrades, backup and access-control duties.
- The integration must degrade safely: an unavailable observability backend must
  not fail inference or weaken policy enforcement.

## Alternatives considered

- Arize Phoenix provides strong open-source, OTel-native tracing and evaluation.
  It remains the preferred fallback if its evaluation workflow better fits later
  requirements; Langfuse was selected for the combined trace, prompt, dataset and
  cost-management workflow needed by this portfolio.
- Provider-native monitoring alone was rejected because it cannot correlate the
  complete multi-provider agent path or hold provider-neutral evaluation evidence.
