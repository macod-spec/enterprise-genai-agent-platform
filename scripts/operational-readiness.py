"""Exercise local recovery and validate operational control evidence."""

import json
import shutil
import tempfile
import time
from pathlib import Path

import yaml

from enterprise_genai_platform.state import SQLiteApprovalStore

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / ".security-reports/operational-readiness.json"
REQUIRED_ALERTS = {
    "AgentGatewayHighErrorRate",
    "AgentGatewayFastErrorBudgetBurn",
    "AgentGatewaySlowErrorBudgetBurn",
    "AgentWorkflowP95LatencyHigh",
    "MCPToolFailures",
    "PendingHumanApprovals",
}
REQUIRED_EVIDENCE = {
    "docs/architecture/overview.md",
    "docs/disaster-recovery.md",
    "docs/ownership.md",
    "docs/privacy-model-risk.md",
    "docs/runbook.md",
    "docs/slo.md",
    "docs/threat-model.md",
}


def recovery_exercise() -> dict[str, float | int | bool]:
    sensitive_query = "synthetic recovery request that must never be retained"
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="agent-platform-dr-") as directory:
        temporary = Path(directory)
        primary = temporary / "primary.db"
        backup = temporary / "backup.db"
        restored = temporary / "restored.db"
        store = SQLiteApprovalStore(str(primary))
        pending = store.create_pending(
            request_id="dr-exercise-request",
            requester="dr-exercise-operator",
            query=sensitive_query,
            tenant="payment-disputes",
        )
        store.close()
        shutil.copy2(primary, backup)
        shutil.copy2(backup, restored)
        recovered = SQLiteApprovalStore(str(restored))
        record = recovered.get(pending.approval_id, tenant="payment-disputes")
        recovered.close()
        if record is None or record.status != "pending":
            raise RuntimeError("restored approval record failed integrity validation")
        if sensitive_query.encode() in backup.read_bytes():
            raise RuntimeError("backup retained sensitive query text")
    return {
        "records_created": 1,
        "records_recovered": 1,
        "records_lost": 0,
        "sensitive_query_absent": True,
        "recovery_seconds": round(time.perf_counter() - started, 4),
    }


def evidence_exercise() -> dict[str, int | bool]:
    missing = [path for path in REQUIRED_EVIDENCE if not (ROOT / path).is_file()]
    if missing:
        raise RuntimeError(f"missing operational evidence: {', '.join(sorted(missing))}")
    alerts = yaml.safe_load((ROOT / "observability/prometheus/alerts.yml").read_text())
    names = {
        rule["alert"]
        for group in alerts.get("groups", [])
        for rule in group.get("rules", [])
        if "alert" in rule
    }
    absent_alerts = REQUIRED_ALERTS - names
    if absent_alerts:
        raise RuntimeError(f"missing required alerts: {', '.join(sorted(absent_alerts))}")
    return {
        "required_documents": len(REQUIRED_EVIDENCE),
        "required_alerts": len(REQUIRED_ALERTS),
        "evidence_complete": True,
    }


def main() -> None:
    report = {"recovery": recovery_exercise(), "evidence": evidence_exercise()}
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
