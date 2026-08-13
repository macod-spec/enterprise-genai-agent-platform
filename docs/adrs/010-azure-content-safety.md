# ADR-010: Content safety enforcement in the model gateway

Status: accepted

## Context

Beyond PII (ADR-009), the platform needs a control for unsafe request or
response content — hate speech, self-harm, sexual content and violence —
independent of and complementary to the PII guard. Per the same principle as
ADR-006 and ADR-009, this belongs in the model gateway, not scattered across
individual agents.

## Decision

Add a content-safety guard to `ModelGateway.generate()`, structurally
parallel to the PII guard: a provider does detection only
(`ContentSafetyProvider.check(text) -> tuple[ContentSafetyFinding, ...]`,
one severity 0-7 per category), and a separate `ContentSafetyPolicy` object
holds per-category severity thresholds and decides what is blocked. Every
request message and every provider response is checked; a category at or
above its threshold raises `ContentSafetyBlockedError` and the call fails
before (request) or instead of (response) reaching the caller.

Two providers:

- `MockContentSafetyProvider` — a deterministic, free keyword classifier for
  local development and CI. It is explicitly documented as not a real safety
  classifier; it exists only to exercise and test the policy/blocking flow
  without a live Azure resource.
- `AzureContentSafetyProvider` — calls Azure AI Content Safety's
  `analyze_text` API via the async SDK, authenticated with
  `DefaultAzureCredential` (no API key read from configuration), matching the
  keyless pattern already used for Azure OpenAI (ADR-006) and following the
  Content Safety SDK's own severity scale (0/2/4/6 by default).

Unlike the PII guard, there is no masking here: content safety is a binary
policy decision per category, not a text-redaction problem, so a block
simply fails the request rather than transforming it.

**Fail closed on provider error.** If the content-safety check itself fails
— timeout, network error, auth failure — the call is treated as blocked
rather than allowed. This is a deliberate asymmetry with Langfuse (ADR-007),
where an unavailable *observability* backend must not affect inference: a
safety *control* is different, and an outage in it should not silently
downgrade to "ungoverned." The same choice governs a missing `severity` value
from Azure: treated as maximum severity (7), not zero.

Audit metadata (a Prometheus counter, the HTTP 400 error detail) carries only
category and action (`blocked` / `provider_error`) — never the analyzed text,
matching the PII guard's audit discipline.

## Consequences

- One more enforcement point in the same place as allowlist, budget and PII,
  keeping ADR-006's "policy lives in the gateway" principle intact through a
  third control.
- On by default (`CONTENT_SAFETY_ENABLED=true`, mock provider) so the policy
  path is always exercised, even without a live Azure resource.
- The fail-closed choice on provider error means a Content Safety outage
  takes down the whole model gateway, not just observability. This is the
  intended trade-off for a safety control but should be revisited if it
  proves too strict in practice (e.g. a circuit breaker that fails open after
  sustained provider errors, with loud alerting).
- `AzureContentSafetyProvider` is now live-verified (2026-08-12): a
  free-tier (F0) `cs-novabank-ai-dev` account was created directly (outside
  Terraform, which does not yet provision one), and a benign string scored
  0 across all four categories while a harmful string was correctly flagged
  and blocked. Full detail in `docs/portfolio/live-verification.md`. No
  adapter bugs were found — the only one of the three live-verified Azure
  adapters that worked correctly on the first real call.

## Alternatives considered

- Running content safety only on the response, not the request: rejected —
  a request that itself contains a bomb threat or self-harm content is worth
  refusing before spending any model-gateway budget or reaching a provider,
  not just filtering what comes back.
- Fail-open on provider error (allow through if the safety check itself is
  unavailable): rejected as inconsistent with the platform's default-deny
  posture elsewhere (MCP tool gateway, model allowlist, budget policy all
  fail closed).
