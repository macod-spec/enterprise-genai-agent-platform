"""API and security-control tests for the local agent gateway."""

import json
import logging
import time
from types import SimpleNamespace
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pydantic import ValidationError

from enterprise_genai_platform.gateway.app import create_app
from enterprise_genai_platform.gateway.config import Settings
from enterprise_genai_platform.gateway.jwt_identity import EntraIdentityResolver
from enterprise_genai_platform.gateway.logging import JsonFormatter, redact


def settings(**overrides: object) -> Settings:
    """Create deterministic settings without reading a developer's local .env file."""
    values: dict[str, object] = {
        "app_env": "test",
        "cors_allowed_origins": ["http://localhost:3000"],
        "rate_limit_requests": 10,
    }
    values.update(overrides)
    return Settings.model_validate(values)


# JWT-mode gateway tests (below) exercise the full app wired for production
# identity, using a synthetic keypair -- see tests/test_jwt_identity.py for
# the resolver's own unit tests and why this split matches every other
# "requires real cloud setup" gate in this project.
_JWT_ISSUER = "https://login.microsoftonline.com/11111111-1111-1111-1111-111111111111/v2.0"
_JWT_AUDIENCE = "api://novabank-agent-platform"
_JWT_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_JWT_PUBLIC_KEY = _JWT_PRIVATE_KEY.public_key()


def _stub_signing_key_resolver(_token: str) -> Any:
    return SimpleNamespace(key=_JWT_PUBLIC_KEY)


def _issue_jwt(*, roles: list[str], subject: str = "alice@novabank.example") -> str:
    now = int(time.time())
    claims = {
        "iss": _JWT_ISSUER,
        "aud": _JWT_AUDIENCE,
        "sub": "oid-alice-1234",
        "preferred_username": subject,
        "iat": now,
        "exp": now + 3600,
        "roles": roles,
    }
    return jwt.encode(claims, _JWT_PRIVATE_KEY, algorithm="RS256")


def test_health_endpoints_are_public_and_secure() -> None:
    client = TestClient(create_app(settings()))

    live = client.get("/health/live", headers={"X-Request-ID": "known-request-1"})
    ready = client.get("/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert ready.json() == {"status": "ready", "checks": {"gateway": "ready"}}
    assert live.headers["x-request-id"] == "known-request-1"
    assert live.headers["x-content-type-options"] == "nosniff"
    assert live.headers["x-frame-options"] == "DENY"
    assert live.headers["cache-control"] == "no-store"
    assert live.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"


def test_invalid_request_id_is_replaced() -> None:
    client = TestClient(create_app(settings()))

    response = client.get("/health/live", headers={"X-Request-ID": "contains spaces"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] != "contains spaces"


def test_protected_route_requires_identity() -> None:
    client = TestClient(create_app(settings()))

    response = client.get("/api/v1/platform/info")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Local"


def test_protected_route_requires_role() -> None:
    client = TestClient(create_app(settings()))

    response = client.get(
        "/api/v1/platform/info",
        headers={"X-Local-User": "developer", "X-Local-Roles": "agent.reader"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Caller does not have the required role"


def test_authorized_local_identity_can_read_platform_info() -> None:
    client = TestClient(create_app(settings()))

    response = client.get(
        "/api/v1/platform/info",
        headers={"X-Local-User": "developer", "X-Local-Roles": "platform.viewer"},
    )

    assert response.status_code == 200
    assert response.json()["authenticated_subject"] == "developer"
    assert response.json()["environment"] == "test"


def test_authorized_caller_can_route_workflow_locally() -> None:
    client = TestClient(create_app(settings()))

    response = client.post(
        "/api/v1/workflows/route",
        headers={"X-Local-User": "developer", "X-Local-Roles": "agent.invoke"},
        json={"query": "Why did this payment fail?"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "decision": {
            "route": "payments",
            "reason": "The request matched payments domain terminology.",
            "confidence": 0.7,
            "requires_human_approval": False,
        },
        "steps": 1,
        "error_code": None,
    }


def test_workflow_route_requires_invoke_role_and_valid_query() -> None:
    client = TestClient(create_app(settings()))

    forbidden = client.post(
        "/api/v1/workflows/route",
        headers={"X-Local-User": "developer", "X-Local-Roles": "platform.viewer"},
        json={"query": "Find a payment"},
    )
    invalid = client.post(
        "/api/v1/workflows/route",
        headers={"X-Local-User": "developer", "X-Local-Roles": "agent.invoke"},
        json={"query": "   "},
    )

    assert forbidden.status_code == 403
    assert invalid.status_code == 422


def test_authorized_caller_can_run_synthetic_investigation() -> None:
    app = create_app(settings())
    client = TestClient(app)

    response = client.post(
        "/api/v1/workflows/investigate",
        headers={
            "X-Local-User": "developer",
            "X-Local-Roles": "agent.invoke",
            "X-Local-Tenant": "payment-disputes",
            "X-Request-ID": "investigation-123",
        },
        json={"query": "Why is CUST-1098 payment transaction TXN-5001 delayed?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"]["route"] == "payments"
    assert payload["result"]["agent"] == "payments"
    assert payload["result"]["evidence"][0]["source_id"] == "TXN-5001"
    assert payload["steps"] == 2
    audit = app.state.mcp_gateway.audit.records[-1]
    assert audit.subject == "developer"
    assert audit.agent == "payments"
    assert audit.request_id == "investigation-123"


def test_investigation_endpoint_prevents_high_risk_execution() -> None:
    client = TestClient(create_app(settings()))

    response = client.post(
        "/api/v1/workflows/investigate",
        headers={
            "X-Local-User": "developer",
            "X-Local-Roles": "agent.invoke",
            "X-Local-Tenant": "payment-disputes",
        },
        json={"query": "Send a refund of £750 for TXN-5001"},
    )

    assert response.status_code == 200
    assert response.json()["result"]["agent"] == "human_review"
    assert response.json()["result"]["requires_human_approval"] is True


def test_local_headers_are_rejected_outside_local_or_test() -> None:
    client = TestClient(create_app(settings(app_env="development")))

    response = client.get(
        "/api/v1/platform/info",
        headers={"X-Local-User": "developer", "X-Local-Roles": "platform.viewer"},
    )

    assert response.status_code == 503
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_jwt_configured_but_no_bearer_token_still_fails_closed() -> None:
    """A client sending X-Local-Tenant with no Authorization header must be
    rejected outright, not silently fall back to trusting the header."""
    app = create_app(
        settings(
            app_env="development",
            jwt_jwks_uri="https://login.microsoftonline.com/test/discovery/v2.0/keys",
            jwt_issuer=_JWT_ISSUER,
            jwt_audience=_JWT_AUDIENCE,
        )
    )
    app.state.jwt_identity_resolver = EntraIdentityResolver(
        jwks_uri="https://login.microsoftonline.com/test/discovery/v2.0/keys",
        issuer=_JWT_ISSUER,
        audience=_JWT_AUDIENCE,
        registry=app.state.tenant_registry,
        signing_key_resolver=_stub_signing_key_resolver,
    )
    client = TestClient(app)

    response = client.get("/api/v1/skills", headers={"X-Local-Tenant": "payment-disputes"})

    assert response.status_code == 401


def test_jwt_mode_ignores_a_client_supplied_tenant_header_entirely() -> None:
    """The regression this whole feature exists to fix: a client-controlled
    X-Local-Tenant header must have zero influence once JWT mode is active
    -- only a validated token's role claim may decide the tenant. The token
    below claims kyc-review; the header claims payment-disputes. If the
    header won any influence at all, this would return payment-disputes'
    two skills instead of kyc-review's one."""
    app = create_app(
        settings(
            app_env="development",
            jwt_jwks_uri="https://login.microsoftonline.com/test/discovery/v2.0/keys",
            jwt_issuer=_JWT_ISSUER,
            jwt_audience=_JWT_AUDIENCE,
        )
    )
    app.state.jwt_identity_resolver = EntraIdentityResolver(
        jwks_uri="https://login.microsoftonline.com/test/discovery/v2.0/keys",
        issuer=_JWT_ISSUER,
        audience=_JWT_AUDIENCE,
        registry=app.state.tenant_registry,
        signing_key_resolver=_stub_signing_key_resolver,
    )
    client = TestClient(app)
    token = _issue_jwt(roles=["platform.viewer", "kyc-review"])

    response = client.get(
        "/api/v1/skills",
        headers={
            "Authorization": f"Bearer {token}",
            # A caller attempting exactly the impersonation this feature
            # closes: claim to be a different tenant via the old header.
            "X-Local-Tenant": "payment-disputes",
        },
    )

    assert response.status_code == 200
    assert {skill["name"] for skill in response.json()["skills"]} == {"customer-profile"}


def test_jwt_mode_rejects_a_tampered_token() -> None:
    app = create_app(
        settings(
            app_env="development",
            jwt_jwks_uri="https://login.microsoftonline.com/test/discovery/v2.0/keys",
            jwt_issuer=_JWT_ISSUER,
            jwt_audience=_JWT_AUDIENCE,
        )
    )
    app.state.jwt_identity_resolver = EntraIdentityResolver(
        jwks_uri="https://login.microsoftonline.com/test/discovery/v2.0/keys",
        issuer=_JWT_ISSUER,
        audience=_JWT_AUDIENCE,
        registry=app.state.tenant_registry,
        signing_key_resolver=_stub_signing_key_resolver,
    )
    client = TestClient(app)
    token = _issue_jwt(roles=["kyc-review"])

    response = client.get(
        "/api/v1/skills", headers={"Authorization": f"Bearer {token}not-the-real-signature"}
    )

    assert response.status_code == 401


def test_request_body_limit_is_enforced_before_route_handling() -> None:
    client = TestClient(create_app(settings(max_request_body_bytes=1_024)))

    response = client.request(
        "POST",
        "/does-not-exist",
        content=b"x" * 1_025,
        headers={"Content-Type": "application/octet-stream"},
    )

    assert response.status_code == 413


def test_rate_limit_is_applied_per_authenticated_subject() -> None:
    client = TestClient(create_app(settings(rate_limit_requests=1)))
    headers = {"X-Local-User": "developer", "X-Local-Roles": "platform.viewer"}

    assert client.get("/api/v1/platform/info", headers=headers).status_code == 200
    limited = client.get("/api/v1/platform/info", headers=headers)

    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"


def test_demo_routes_are_rate_limited_even_without_identity_headers() -> None:
    """The demo routes accept no auth headers (browsers can't set them), so
    with no IP allowlist on the deployment, source-IP rate limiting is the
    only thing standing between this surface and unbounded model spend."""
    client = TestClient(create_app(settings(rate_limit_requests=1)))
    data = {
        "query": "Why is CUST-1098 payment transaction TXN-5001 delayed?",
        "tenant": "payment-disputes",
    }

    first = client.post("/api/v1/demo/investigate", data=data)
    limited = client.post("/api/v1/demo/investigate", data=data)

    assert first.status_code == 200
    assert limited.status_code == 429


def test_cors_allows_only_configured_origin() -> None:
    client = TestClient(create_app(settings()))

    allowed = client.options(
        "/api/v1/platform/info",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    denied = client.options(
        "/api/v1/platform/info",
        headers={
            "Origin": "https://attacker.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-origin" not in denied.headers


def test_wildcard_cors_configuration_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Wildcard CORS origins are not permitted"):
        settings(cors_allowed_origins=["*"])


def test_structured_logging_redacts_sensitive_fields() -> None:
    # fmt: off
    sensitive_fields = {"token": "x", "nested": {"password": "x"}}  # pragma: allowlist secret
    # fmt: on
    assert redact(sensitive_fields) == {
        "token": "[REDACTED]",  # pragma: allowlist secret
        "nested": {"password": "[REDACTED]"},  # pragma: allowlist secret
    }

    record = logging.LogRecord("gateway", logging.INFO, "", 0, "event", (), None)
    record.event_fields = {  # pragma: allowlist secret
        "request_id": "request-1",
        "authorization": "private",
    }
    payload = json.loads(JsonFormatter().format(record))

    assert payload["request_id"] == "request-1"
    assert payload["authorization"] == "[REDACTED]"


def test_demo_page_is_reachable_without_headers() -> None:
    """Unlike the JSON API, the browser demo form needs no X-Local-* headers —
    browser forms cannot set custom headers."""
    app = create_app(settings())
    client = TestClient(app)

    response = client.get("/api/v1/demo")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<form" in response.text


def test_demo_investigate_form_runs_the_real_workflow_with_a_fixed_identity() -> None:
    app = create_app(settings())
    client = TestClient(app)

    response = client.post(
        "/api/v1/demo/investigate",
        data={
            "query": "Why is CUST-1098 payment transaction TXN-5001 delayed?",
            "tenant": "payment-disputes",
        },
    )

    assert response.status_code == 200
    assert "CUST-1098" in response.text or "customer" in response.text.lower()


def test_demo_pages_escape_user_supplied_text() -> None:
    """A query containing HTML-significant characters must never be reflected
    unescaped into the response — this is a browser-facing surface."""
    app = create_app(settings())
    client = TestClient(app)

    response = client.post(
        "/api/v1/demo/investigate",
        data={"query": "<script>alert(1)</script>", "tenant": "payment-disputes"},
    )

    assert response.status_code == 200
    assert "<script>alert(1)</script>" not in response.text


def test_demo_rag_form_renders_citations_for_real_hits() -> None:
    """Regression test: this route 500'd in production the first time it hit a
    real backend with non-empty evidence.hits, because it called html.escape()
    on the whole Citation object instead of its chunk_id string field. No test
    exercised this path with real hits before — the mock/local-index tests
    that did run never happened to produce any."""
    app = create_app(settings())
    client = TestClient(app)

    response = client.post(
        "/api/v1/demo/rag",
        data={
            "query": "delayed faster payment acknowledgement escalation",
            "tenant": "payment-disputes",
        },
    )

    assert response.status_code == 200
    assert "<li>POL-PAY-001" in response.text
