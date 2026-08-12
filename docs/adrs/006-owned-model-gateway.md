# ADR-006: Own a thin model gateway

Status: accepted

## Context

The platform needs one enforcement point for model allowlists, tenant and agent
budgets, token/cost attribution, request correlation, safety policy and provider
failover. A general-purpose proxy can accelerate provider compatibility, but it
cannot own NovaBank-specific authorization, governance evidence or cost policy.

## Decision

Build and maintain a thin Python gateway inside this repository. It exposes a
small provider-neutral application contract and delegates actual inference to
provider adapters. Authentication, authorization, quotas, policy decisions and
OpenTelemetry emission remain first-class application code with executable tests.

The gateway will not reimplement provider SDKs or an OpenAI-compatible API. A
third-party proxy may later sit behind the adapter boundary if the number of
providers makes its operational and supply-chain cost worthwhile.

## Consequences

- The platform can prove fail-closed controls and per-tenant cost attribution in CI.
- Domain policy stays reviewable and is not hidden in proxy configuration.
- We accept ownership of a small security-critical service and must keep its surface
  narrow, dependency-locked, threat-modelled and load-tested.
- Provider-specific retry and streaming behavior stays isolated in adapters.

## Alternatives considered

- Adopt a model proxy such as LiteLLM as the platform control plane. This offers
  broad provider compatibility, but adds a large privileged dependency and still
  requires custom governance integration.
- Call model providers directly from each agent. Rejected because enforcement and
  telemetry would be duplicated and could be bypassed.

## Implementation status

Implemented in `src/enterprise_genai_platform/model_gateway/`: a provider-neutral
`ChatModelProvider` contract, a deny-by-default model allowlist, an in-process
per-tenant GBP budget ceiling that fails closed, a deterministic zero-cost mock
adapter, a keyless Azure OpenAI adapter (`DefaultAzureCredential`, no embedded API
key), GenAI OpenTelemetry semantic-convention spans, and Prometheus token/cost/
latency metrics. The gateway is wired into the agent HTTP API as
`POST /api/v1/model-gateway/generate` and exercised by unit and HTTP-level tests
using the mock provider (`tests/test_model_gateway.py`).

Unverified: the Azure OpenAI adapter has not yet made a real call against a live
Azure OpenAI deployment (blocked on the same subscription/quota constraints as
AKS) and the in-process budget ledger is not durable across gateway replicas.
Both are tracked as follow-up work before this gateway is relied on for
production multi-tenant cost enforcement.
