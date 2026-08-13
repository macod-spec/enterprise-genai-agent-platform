"""Metrics coverage and sensitive-label regression tests."""

from fastapi.testclient import TestClient

from enterprise_genai_platform.gateway.app import create_app
from enterprise_genai_platform.gateway.config import Settings
from enterprise_genai_platform.metrics import safe_error_code


def test_metrics_cover_gateway_workflow_mcp_rag_and_model_without_sensitive_labels() -> None:
    app = create_app(Settings.model_validate({"app_env": "test", "metrics_enabled": True}))
    client = TestClient(app)
    query = "Find the delayed payment policy procedure"

    response = client.post(
        "/api/v1/workflows/investigate",
        headers={
            "X-Local-User": "metrics-user",
            "X-Local-Roles": "agent.invoke",
            "X-Local-Tenant": "payment-disputes",
            "X-Request-ID": "sensitive-request-id",
        },
        json={"query": query},
    )
    metrics = client.get("/metrics")

    assert response.status_code == 200
    assert metrics.status_code == 200
    body = metrics.text
    assert "agent_platform_http_requests_total" in body
    assert "agent_platform_workflow_completions_total" in body
    assert "agent_platform_mcp_calls_total" in body
    assert "agent_platform_rag_retrievals_total" in body
    assert "agent_platform_model_tokens_total" in body
    assert query not in body
    assert "metrics-user" not in body
    assert "sensitive-request-id" not in body


def test_metrics_can_be_disabled_and_error_labels_are_bounded() -> None:
    app = create_app(Settings.model_validate({"app_env": "test", "metrics_enabled": False}))

    assert TestClient(app).get("/metrics").status_code == 404
    assert safe_error_code("attacker-controlled-value") == "other"
    assert safe_error_code("POLICY_NOT_FOUND") == "POLICY_NOT_FOUND"
