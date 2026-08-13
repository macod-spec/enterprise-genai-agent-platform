"""FastAPI application factory for the agent gateway."""

import html
import time
from typing import Annotated

from fastapi import Depends, FastAPI, Form, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from enterprise_genai_platform import __version__
from enterprise_genai_platform.agents import CustomerAgent, PaymentsAgent, PolicyAgent
from enterprise_genai_platform.domain import NovaBankRepository
from enterprise_genai_platform.gateway.auth import (
    InMemoryRateLimiter,
    Principal,
    TenantScoped,
    enforce_demo_rate_limit,
    enforce_rate_limit,
    require_roles,
)
from enterprise_genai_platform.gateway.config import Settings, get_settings
from enterprise_genai_platform.gateway.jwt_identity import EntraIdentityResolver
from enterprise_genai_platform.gateway.logging import configure_logging
from enterprise_genai_platform.gateway.middleware import RequestSecurityMiddleware
from enterprise_genai_platform.gateway.models import (
    HealthResponse,
    InvestigationResponse,
    ModelGenerateRequest,
    ModelGenerateResponse,
    PlatformInfoResponse,
    RagAnswerRequest,
    RagAnswerResponse,
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
from enterprise_genai_platform.model_gateway import (
    ModelBudgetExceeded,
    ModelGenerationRequest,
    ModelNotAllowed,
    ModelProviderFailure,
    build_model_gateway,
)
from enterprise_genai_platform.models import DeterministicMockModel
from enterprise_genai_platform.observability import configure_observability
from enterprise_genai_platform.orchestration import OperationsWorkflow, SupervisorWorkflow
from enterprise_genai_platform.rag import build_retriever
from enterprise_genai_platform.rag.groundedness import GroundednessEvaluator
from enterprise_genai_platform.rag.synthesis import synthesize_grounded_answer
from enterprise_genai_platform.safety.content_safety import ContentSafetyBlockedError
from enterprise_genai_platform.safety.pii import PiiBlockedError
from enterprise_genai_platform.skills import build_default_skill_registry
from enterprise_genai_platform.state import build_approval_store
from enterprise_genai_platform.tenancy.context import TenantContext
from enterprise_genai_platform.tenancy.registry import (
    UnknownTenantError,
    build_default_tenant_registry,
)

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
    retriever = build_retriever(runtime_settings)
    mcp_gateway = build_local_mcp_gateway(
        repository,
        retriever=retriever,
        timeout_seconds=runtime_settings.mcp_tool_timeout_seconds,
        max_attempts=runtime_settings.mcp_max_attempts,
        rate_limit=runtime_settings.mcp_rate_limit,
        rate_window_seconds=runtime_settings.mcp_rate_window_seconds,
    )
    app.state.mcp_gateway = mcp_gateway
    app.state.retriever = retriever
    app.state.groundedness_evaluator = GroundednessEvaluator(
        minimum_term_overlap=runtime_settings.rag_groundedness_minimum_term_overlap
    )
    app.state.skill_registry = build_default_skill_registry()
    app.state.tenant_registry = build_default_tenant_registry()
    if (
        runtime_settings.jwt_jwks_uri
        and runtime_settings.jwt_issuer
        and runtime_settings.jwt_audience
    ):
        app.state.jwt_identity_resolver = EntraIdentityResolver(
            jwks_uri=runtime_settings.jwt_jwks_uri,
            issuer=runtime_settings.jwt_issuer,
            audience=runtime_settings.jwt_audience,
            registry=app.state.tenant_registry,
            tenant_claim=runtime_settings.jwt_tenant_claim,
        )
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
    app.state.model_gateway = build_model_gateway(
        runtime_settings, tenant_registry=app.state.tenant_registry
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
        tenant_context: TenantScoped,
        request: Request,
    ) -> InvestigationResponse:
        started = time.perf_counter()
        result = await app.state.operations.investigate(
            payload.query,
            subject=principal.subject,
            # Union, not replace: principal.roles is the MCP tool-invocation
            # capability gate (e.g. agent.invoke), while the tenant bundle's
            # entitlements are the document-retrieval scope the specialist
            # policy agent's RAG search checks. Both checks are subset tests
            # against this one set, so neither is weakened by the other's
            # presence — a caller still needs agent.invoke to call any tool,
            # and still only sees documents within its own tenant's domains.
            roles=principal.roles | tenant_context.bundle.entitlements,
            request_id=request.state.request_id,
        )
        approval_id = None
        if result.result.requires_human_approval:
            approval = app.state.approvals.create_pending(
                request_id=request.state.request_id,
                requester=principal.subject,
                query=payload.query,
                tenant=tenant_context.tenant,
            )
            approval_id = approval.approval_id
        WORKFLOW_COMPLETIONS.labels(
            tenant_context.tenant,
            result.decision.route,
            result.result.agent,
            str(result.result.requires_human_approval).lower(),
            safe_error_code(result.result.error_code or "none"),
        ).inc()
        WORKFLOW_DURATION.labels(tenant_context.tenant, result.decision.route).observe(
            time.perf_counter() - started
        )
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
    async def list_skills(
        _principal: PlatformViewer, tenant_context: TenantScoped
    ) -> SkillListResponse:
        allowed = tenant_context.bundle.allowed_skills
        return SkillListResponse(
            skills=tuple(
                skill for skill in app.state.skill_registry.list_approved() if skill.name in allowed
            )
        )

    @app.post(
        f"{runtime_settings.api_prefix}/model-gateway/generate",
        response_model=ModelGenerateResponse,
        tags=["model-gateway"],
        dependencies=[Depends(enforce_rate_limit)],
    )
    async def generate(
        payload: ModelGenerateRequest, _principal: AgentInvoker, tenant_context: TenantScoped
    ) -> ModelGenerateResponse:
        request = ModelGenerationRequest(
            model=payload.model,
            messages=payload.messages,
            tenant=tenant_context.tenant,
            agent="model-gateway-api",
            max_tokens=payload.max_tokens,
            temperature=payload.temperature,
        )
        try:
            result = await app.state.model_gateway.generate(request)
        except (ModelNotAllowed, ModelBudgetExceeded) as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        except PiiBlockedError as exc:
            # Entity type labels only (e.g. "CREDIT_CARD"); never the matched value.
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except ContentSafetyBlockedError as exc:
            # Category labels only (e.g. "Violence"); never the analyzed text.
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except ModelProviderFailure as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The model provider is currently unavailable",
            ) from exc
        return ModelGenerateResponse(
            content=result.content,
            model=result.model,
            provider=result.provider,
            usage=result.usage,
            estimated_cost_gbp=result.estimated_cost_gbp,
            finish_reason=result.finish_reason,
        )

    @app.post(
        f"{runtime_settings.api_prefix}/rag/answer",
        response_model=RagAnswerResponse,
        tags=["rag"],
        dependencies=[Depends(enforce_rate_limit)],
    )
    async def rag_answer(
        payload: RagAnswerRequest, _principal: AgentInvoker, tenant_context: TenantScoped
    ) -> RagAnswerResponse:
        # Tenant entitlements, not the caller's individual roles, gate
        # retrieval: this is what makes a document scoped to one tenant
        # invisible to every other tenant regardless of which of that
        # tenant's users is asking.
        evidence = await app.state.retriever.retrieve(
            payload.query, caller_roles=tenant_context.bundle.entitlements
        )
        try:
            answer = await synthesize_grounded_answer(
                app.state.model_gateway,
                model=runtime_settings.rag_synthesis_model,
                query=payload.query,
                evidence=evidence,
                tenant=tenant_context.tenant,
            )
        except (ModelNotAllowed, ModelBudgetExceeded) as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        except PiiBlockedError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except ContentSafetyBlockedError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except ModelProviderFailure as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The model provider is currently unavailable",
            ) from exc
        report = app.state.groundedness_evaluator.evaluate(answer, evidence)
        return RagAnswerResponse(
            answer=answer,
            citations=tuple(hit.citation for hit in evidence.hits),
            term_overlap_score=report.term_overlap_score,
            citations_found=report.citations_found,
            fabricated_citations=report.fabricated_citations,
            is_grounded=report.is_grounded,
        )

    # A plain HTML/form demo surface, not a JSON API. Deliberately no
    # inline <script> or <style>: the platform's strict
    # Content-Security-Policy (default-src 'none', set unconditionally by
    # RequestSecurityMiddleware) would block them, and this route does not
    # get a security exemption. Plain <form method="post"> submission needs
    # no script execution, so nothing here requires weakening that policy.
    # Browser forms cannot set the X-Local-User/X-Local-Roles headers the
    # JSON API uses for identity, so this surface authenticates as a fixed
    # demo principal instead — there is no IP allowlist gating it (a
    # rotating home IP is unsuitable as an access control and would itself
    # be a leak surface). Real controls for this surface specifically:
    # enforce_demo_rate_limit (per-source-IP, since there is no subject to
    # key on) and the per-tenant token budget, which caps spend regardless
    # of caller identity.
    _demo_principal = Principal(subject="browser-demo", roles=frozenset({"agent.invoke"}))

    def _demo_tenant_options() -> str:
        return "".join(
            f'<option value="{html.escape(name)}">{html.escape(name)}</option>'
            for name in sorted(app.state.tenant_registry.names())
        )

    def _demo_tenant(tenant: str) -> TenantContext:
        try:
            bundle = app.state.tenant_registry.get(tenant)
        except UnknownTenantError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return TenantContext(tenant=tenant, bundle=bundle)

    def _demo_page(result_html: str = "") -> HTMLResponse:
        prefix = runtime_settings.api_prefix
        tenant_options = _demo_tenant_options()
        return HTMLResponse(f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>NovaBank AI Agent Platform — Demo</title></head>
<body>
<h1>NovaBank AI Agent Platform — Live Demo</h1>
<p>Synthetic data only. Requests here run as a fixed demo user identity
(subject=browser-demo, roles=agent.invoke) acting on behalf of whichever
tenant you pick below; access to this deployment is controlled by IP
restriction, not this form. Switching the tenant changes what the same
question can retrieve — that isolation is enforced server-side, not by
this form hiding options.</p>

<h2>Investigate a customer</h2>
<form method="post" action="{prefix}/demo/investigate">
  <label>Tenant: <select name="tenant">{tenant_options}</select></label>
  <label>Query:
    <input type="text" name="query" size="60"
           value="Look up account status for customer CUST-1098">
  </label>
  <button type="submit">Investigate</button>
</form>

<h2>Ask a policy question</h2>
<form method="post" action="{prefix}/demo/rag">
  <label>Tenant: <select name="tenant">{tenant_options}</select></label>
  <label>Query:
    <input type="text" name="query" size="60"
           value="What is required before a refund above GBP 100 can be approved?">
  </label>
  <button type="submit">Ask</button>
</form>

{result_html}
</body>
</html>""")

    @app.get(f"{runtime_settings.api_prefix}/demo", include_in_schema=False)
    async def demo_page() -> HTMLResponse:
        return _demo_page()

    @app.post(
        f"{runtime_settings.api_prefix}/demo/investigate",
        include_in_schema=False,
        dependencies=[Depends(enforce_demo_rate_limit)],
    )
    async def demo_investigate(
        request: Request, query: Annotated[str, Form()], tenant: Annotated[str, Form()]
    ) -> HTMLResponse:
        tenant_context = _demo_tenant(tenant)
        outcome = await app.state.operations.investigate(
            query,
            subject=_demo_principal.subject,
            roles=_demo_principal.roles | tenant_context.bundle.entitlements,
            request_id=request.state.request_id,
        )
        if outcome.result.requires_human_approval:
            app.state.approvals.create_pending(
                request_id=request.state.request_id,
                requester=_demo_principal.subject,
                query=query,
                tenant=tenant_context.tenant,
            )
        evidence_items = "".join(
            f"<li>{html.escape(item.source_id)} ({html.escape(item.source_type)}): "
            f"{html.escape(item.detail)}</li>"
            for item in outcome.result.evidence
        )
        result_html = f"""
<h2>Result</h2>
<p><b>Route:</b> {html.escape(outcome.decision.route)}
   — {html.escape(outcome.decision.reason)}</p>
<p><b>Agent:</b> {html.escape(outcome.result.agent)}</p>
<p><b>Summary:</b> {html.escape(outcome.result.summary)}</p>
<ul>{evidence_items}</ul>
<p><b>Requires human approval:</b> {outcome.result.requires_human_approval}</p>
"""
        return _demo_page(result_html)

    @app.post(
        f"{runtime_settings.api_prefix}/demo/rag",
        include_in_schema=False,
        dependencies=[Depends(enforce_demo_rate_limit)],
    )
    async def demo_rag(
        query: Annotated[str, Form()], tenant: Annotated[str, Form()]
    ) -> HTMLResponse:
        tenant_context = _demo_tenant(tenant)
        evidence = await app.state.retriever.retrieve(
            query, caller_roles=tenant_context.bundle.entitlements
        )
        try:
            answer = await synthesize_grounded_answer(
                app.state.model_gateway,
                model=runtime_settings.rag_synthesis_model,
                query=query,
                evidence=evidence,
                tenant=tenant_context.tenant,
            )
        except (
            ModelNotAllowed,
            ModelBudgetExceeded,
            PiiBlockedError,
            ContentSafetyBlockedError,
            ModelProviderFailure,
        ) as exc:
            return _demo_page(f"<h2>Blocked</h2><p>{html.escape(str(exc))}</p>")
        report = app.state.groundedness_evaluator.evaluate(answer, evidence)
        citation_items = "".join(
            f"<li>{html.escape(hit.citation.chunk_id)}</li>" for hit in evidence.hits
        )
        answer_html = html.escape(answer) or (
            "<i>(the model returned no visible text — its response budget was "
            "spent on internal reasoning; see docs/portfolio/live-verification.md)</i>"
        )
        result_html = f"""
<h2>Answer</h2>
<p>{answer_html}</p>
<p><b>Grounded:</b> {report.is_grounded}
   (term overlap {report.term_overlap_score:.2f})</p>
<ul>{citation_items}</ul>
"""
        return _demo_page(result_html)

    return app
