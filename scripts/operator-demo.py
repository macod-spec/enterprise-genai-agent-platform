"""Run a deterministic local operator demonstration and emit sanitised evidence."""

import hashlib
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from enterprise_genai_platform.gateway.app import create_app
from enterprise_genai_platform.gateway.config import Settings

ROOT = Path(__file__).resolve().parents[1]
SENSITIVE_QUERY = "Send a refund of £750 for TXN-5001"


def request(
    client: TestClient,
    query: str,
    *,
    roles: str = "agent.invoke",
    request_id: str,
) -> Any:
    return client.post(
        "/api/v1/workflows/investigate",
        headers={
            "X-Local-User": "local-operator",
            "X-Local-Roles": roles,
            "X-Request-ID": request_id,
        },
        json={"query": query},
    )


def main() -> None:
    settings = Settings.model_validate(
        {"app_env": "test", "state_backend": "sqlite", "state_database_path": ":memory:"}
    )
    app = create_app(settings)
    with TestClient(app) as client:
        unauthorised = request(
            client,
            "Show customer CUST-1098 account profile",
            roles="platform.viewer",
            request_id="demo-denied",
        )
        investigation = request(
            client,
            "Why is CUST-1098 payment transaction TXN-5001 delayed?",
            request_id="demo-investigation",
        )
        high_risk = request(client, SENSITIVE_QUERY, request_id="demo-human-review")

        high_risk_payload = high_risk.json()
        approval = app.state.approvals.get(high_risk_payload["approval_id"])
        audit = app.state.mcp_gateway.audit.records[-1]
        query_hash = hashlib.sha256(SENSITIVE_QUERY.encode()).hexdigest()
        checks = {
            "unauthorised_request_denied": unauthorised.status_code == 403,
            "read_only_investigation_succeeded": investigation.status_code == 200
            and investigation.json()["result"]["agent"] == "payments",
            "evidence_is_cited": investigation.json()["result"]["evidence"][0]["source_id"]
            == "TXN-5001",
            "high_risk_action_not_executed": high_risk.status_code == 200
            and high_risk_payload["result"]["agent"] == "human_review",
            "approval_record_created": approval is not None and approval.status == "pending",
            "approval_stores_hash_only": approval is not None
            and approval.query_sha256 == query_hash,
            "tool_call_is_audited": audit.request_id == "demo-investigation"
            and len(audit.argument_fingerprint) == 64,
        }

    report = {
        "scenario": "local-secure-operator-demo",
        "synthetic_data_only": True,
        "external_calls": 0,
        "cloud_resources_created": 0,
        "checks": checks,
        "passed": all(checks.values()),
    }
    report_path = ROOT / ".security-reports/operator-demo.json"
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["passed"]:
        raise RuntimeError("operator demonstration failed")


if __name__ == "__main__":
    main()
