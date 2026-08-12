"""GenAI OpenTelemetry semantic-convention spans and cost/token metrics.

Prompt and completion text are never attached to spans or metrics; only
model identity, token counts, cost and outcome are recorded. This matches
the platform's default of not collecting payload content (see ADR-007).
"""

from collections.abc import Iterable, Iterator
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode

from enterprise_genai_platform.metrics import (
    CONTENT_SAFETY_FINDINGS,
    MODEL_ESTIMATED_COST_GBP,
    MODEL_GATEWAY_CALLS,
    MODEL_GATEWAY_DURATION,
    MODEL_TOKENS,
    PII_FINDINGS,
)
from enterprise_genai_platform.model_gateway.contracts import (
    ModelGenerationRequest,
    ModelGenerationResult,
)

_TRACER = trace.get_tracer("enterprise_genai_platform.model_gateway")


@contextmanager
def generation_span(request: ModelGenerationRequest, *, provider: str) -> Iterator[Span]:
    """Open a GenAI semantic-convention span scoped to one generation call."""
    with _TRACER.start_as_current_span(
        f"chat {request.model}",
        kind=SpanKind.CLIENT,
        attributes={
            "gen_ai.system": provider,
            "gen_ai.request.model": request.model,
            "gen_ai.request.max_tokens": request.max_tokens,
            "gen_ai.request.temperature": request.temperature,
            "enterprise.tenant": request.tenant,
            "enterprise.agent": request.agent,
        },
    ) as span:
        yield span


def record_success(span: Span, result: ModelGenerationResult) -> None:
    """Attach GenAI response attributes and emit token/cost/latency metrics."""
    span.set_attribute("gen_ai.response.model", result.model)
    span.set_attribute("gen_ai.response.finish_reasons", (result.finish_reason,))
    span.set_attribute("gen_ai.usage.input_tokens", result.usage.prompt_tokens)
    span.set_attribute("gen_ai.usage.output_tokens", result.usage.completion_tokens)
    span.set_status(Status(StatusCode.OK))

    MODEL_TOKENS.labels(result.provider, "input").inc(result.usage.prompt_tokens)
    MODEL_TOKENS.labels(result.provider, "output").inc(result.usage.completion_tokens)
    MODEL_ESTIMATED_COST_GBP.labels(result.provider).inc(result.estimated_cost_gbp)
    MODEL_GATEWAY_CALLS.labels(result.model, result.provider, "success").inc()
    MODEL_GATEWAY_DURATION.labels(result.model, result.provider).observe(result.latency_seconds)


def record_failure(
    span: Span,
    *,
    model: str,
    provider: str,
    outcome: str,
    duration_seconds: float,
) -> None:
    """Mark the span as failed and emit outcome/latency metrics without cost or tokens."""
    span.set_status(Status(StatusCode.ERROR, outcome))
    MODEL_GATEWAY_CALLS.labels(model, provider, outcome).inc()
    MODEL_GATEWAY_DURATION.labels(model, provider).observe(duration_seconds)


def record_pii_findings(entity_types: Iterable[str], *, action: str) -> None:
    """Record detected-entity type and action only; never the matched text."""
    for entity_type in entity_types:
        PII_FINDINGS.labels(entity_type, action).inc()


def record_content_safety_findings(categories: Iterable[str], *, action: str) -> None:
    """Record category and action only; never the analyzed text."""
    for category in categories:
        CONTENT_SAFETY_FINDINGS.labels(category, action).inc()
