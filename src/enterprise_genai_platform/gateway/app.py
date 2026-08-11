"""FastAPI application factory for the agent gateway."""

import time
from typing import Annotated

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from enterprise_genai_platform import __version__
from enterprise_genai_platform.agents import CustomerAgent, PaymentsAgent, PolicyAgent
from enterprise_genai_platform.domain import NovaBankRepository
from enterprise_genai_platform.gateway.auth import (
    InMemoryRateLimiter,
    Principal,
    enforce_rate_limit,
    require_roles,
)
from enterprise_genai_platform.gateway.config import Settings, get_settings
from enterprise_genai_platform.gateway.logging import configure_logging
from enterprise_genai_platform.gateway.middleware import RequestSecurityMiddleware
from enterprise_genai_platform.gateway.models import (
    HealthResponse,
    InvestigationResponse,
    PlatformInfoResponse,
    ReadinessResponse,
    RouteRequest,
    RouteResponse,
    SkillListResponse,
)
from enterprise_genai_platform.mcp_boundary import build_local_mcp_gateway
from enterprise_genai_platform.metrics import (
    WORKFLOW_COMPLETIONS,
    WORKFLOW_DURATION,
    safe_error_code,
)
from enterprise_genai_platform.models import DeterministicMockModel
from enterprise_genai_platform.observability import configure_observability
from enterprise_genai_platform.orchestration import OperationsWorkflow, SupervisorWorkflow
from enterprise_genai_platform.skills import build_default_skill_registry
from enterprise_genai_platform.state import build_approval_store

PlatformViewer = Annotated[Principal, Depends(require_roles("platform.viewer"))]
AgentInvoker = Annotated[Principal, Depends(require_roles("agent.invoke"))]


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an isolated gateway instance for production or tests."""
    runtime_settings = settings or get_settings()
    configure_logging(runtime_settings.log_level)

    app = FastAPI(
        title=runtime_settings.app_name,
        version=__version__,
        docs_url="/docs" if runtime_settings.app_env in {"local", "test"} else None,
        redoc_url=None,
        openapi_url="/openapi.json" if runtime_settings.app_env in {"local", "test"} else None,
    )
    app.state.settings = runtime_settings
    app.state.rate_limiter = InMemoryRateLimiter(
        runtime_settings.rate_limit_requests,
        runtime_settings.rate_limit_window_seconds,
    )
    model = DeterministicMockModel()
    repository = NovaBankRepository()
    mcp_gateway = build_local_mcp_gateway(
        repository,
        timeout_seconds=runtime_settings.mcp_tool_timeout_seconds,
        max_attempts=runtime_settings.mcp_max_attempts,
        rate_limit=runtime_settings.mcp_rate_limit,
        rate_window_seconds=runtime_settings.mcp_rate_window_seconds,
    )
    app.state.mcp_gateway = mcp_gateway
    app.state.skill_registry = build_default_skill_registry()
    connection_url = (
        runtime_settings.state_connection_url.get_secret_value()
        if runtime_settings.state_connection_url
        else None
    )
    app.state.approvals = build_approval_store(
        runtime_settings.state_backend,
        sqlite_path=runtime_settings.state_database_path,
        connection_url=connection_url,
    )
    app.state.supervisor = SupervisorWorkflow(
        model,
        max_steps=runtime_settings.max_workflow_steps,
    )
    app.state.operations = OperationsWorkflow(
        model,
        CustomerAgent(mcp_gateway),
        PaymentsAgent(mcp_gateway),
        PolicyAgent(mcp_gateway),
        max_steps=runtime_settings.max_workflow_steps,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime_settings.cors_allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Local-User", "X-Local-Roles", "X-Request-ID"],
    )
    app.add_middleware(
        RequestSecurityMiddleware,
        max_body_bytes=runtime_settings.max_request_body_bytes,
        timeout_seconds=runtime_settings.request_timeout_seconds,
    )
    configure_observability(
        app,
        export_enabled=runtime_settings.otel_export_enabled,
        endpoint=runtime_settings.otel_exporter_otlp_endpoint,
    )

    @app.get("/health/live", response_model=HealthResponse, tags=["health"])
    async def liveness() -> HealthResponse:
        return HealthResponse()

    @app.get("/health/ready", response_model=ReadinessResponse, tags=["health"])
    async def readiness() -> ReadinessResponse:
        return ReadinessResponse(checks={"gateway": "ready"})

    if runtime_settings.metrics_enabled:

        @app.get("/metrics", include_in_schema=False)
        async def metrics() -> Response:
            return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get(
        f"{runtime_settings.api_prefix}/platform/info",
        response_model=PlatformInfoResponse,
        tags=["platform"],
        dependencies=[Depends(enforce_rate_limit)],
    )
    async def platform_info(principal: PlatformViewer) -> PlatformInfoResponse:
        return PlatformInfoResponse(
            name=runtime_settings.app_name,
            environment=runtime_settings.app_env,
            authenticated_subject=principal.subject,
        )

    @app.post(
        f"{runtime_settings.api_prefix}/workflows/route",
        response_model=RouteResponse,
        tags=["workflows"],
        dependencies=[Depends(enforce_rate_limit)],
    )
    async def route_workflow(payload: RouteRequest, _principal: AgentInvoker) -> RouteResponse:
        result = await app.state.supervisor.route(payload.query)
        return RouteResponse(
            decision=result.decision,
            steps=result.steps,
            error_code=result.error_code,
        )

    @app.post(
        f"{runtime_settings.api_prefix}/workflows/investigate",
        response_model=InvestigationResponse,
        tags=["workflows"],
        dependencies=[Depends(enforce_rate_limit)],
    )
    async def investigate_workflow(
        payload: RouteRequest,
        principal: AgentInvoker,
        request: Request,
    ) -> InvestigationResponse:
        started = time.perf_counter()
        result = await app.state.operations.investigate(
            payload.query,
            subject=principal.subject,
            roles=principal.roles,
            request_id=request.state.request_id,
        )
        approval_id = None
        if result.result.requires_human_approval:
            approval = app.state.approvals.create_pending(
                request_id=request.state.request_id,
                requester=principal.subject,
                query=payload.query,
            )
            approval_id = approval.approval_id
        WORKFLOW_COMPLETIONS.labels(
            result.decision.route,
            result.result.agent,
            str(result.result.requires_human_approval).lower(),
            safe_error_code(result.result.error_code or "none"),
        ).inc()
        WORKFLOW_DURATION.labels(result.decision.route).observe(time.perf_counter() - started)
        return InvestigationResponse(
            decision=result.decision,
            result=result.result,
            steps=result.steps,
            approval_id=approval_id,
        )

    @app.get(
        f"{runtime_settings.api_prefix}/skills",
        response_model=SkillListResponse,
        tags=["governance"],
        dependencies=[Depends(enforce_rate_limit)],
    )
    async def list_skills(_principal: PlatformViewer) -> SkillListResponse:
        return SkillListResponse(skills=app.state.skill_registry.list_approved())

    return app
