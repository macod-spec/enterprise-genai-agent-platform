"""Vendor-neutral tracing configured to remain offline unless explicitly enabled."""

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def configure_observability(
    app: FastAPI,
    *,
    export_enabled: bool,
    endpoint: str,
) -> None:
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": "enterprise-agent-gateway",
                "service.version": app.version,
                "deployment.environment": app.state.settings.app_env,
            }
        )
    )
    if export_enabled:
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=endpoint.startswith("http://"))
        provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=provider,
        excluded_urls="/health/live,/health/ready",
    )
