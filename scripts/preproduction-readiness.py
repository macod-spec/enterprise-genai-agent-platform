"""Audit local evidence before any provider-connected Azure planning is considered."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    required = (
        "docs/azure-sandbox-cost-review.md",
        "docs/azure-private-module-design.md",
        "docs/azure-identity-network-review.md",
        "docs/preproduction-readiness.md",
        "infrastructure/terraform/backend.hcl.example",
        "config/azure-retail-price-snapshot.json",
        ".security-reports/terraform-zero-plan.json",
    )
    checks = {f"file:{path}": (ROOT / path).is_file() for path in required}
    backend = (ROOT / "infrastructure/terraform/backend.hcl.example").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yaml").read_text(encoding="utf-8")
    executable_steps = "\n".join(
        line for line in workflow.splitlines() if line.lstrip().startswith("- run:")
    )
    zero_plan = json.loads(
        (ROOT / ".security-reports/terraform-zero-plan.json").read_text(encoding="utf-8")
    )
    price_snapshot = json.loads(
        (ROOT / "config/azure-retail-price-snapshot.json").read_text(encoding="utf-8")
    )
    checks.update(
        {
            "state_uses_oidc": "use_oidc             = true" in backend,
            "state_uses_azuread": "use_azuread_auth     = true" in backend,
            "ci_has_no_azure_login": "azure/login" not in workflow and "az login" not in workflow,
            "ci_has_no_apply": "terraform apply" not in executable_steps,
            "default_plan_zero_changes": zero_plan["resource_changes"] == 0,
            "default_plan_created_nothing": zero_plan["cloud_resources_created"] == 0,
            "non_zero_plan_cost_blocked": price_snapshot["within_budget"] is False,
        }
    )
    report = {
        "checks": checks,
        "local_preparation_complete": all(checks.values()),
        "connected_plan_approved": False,
        "cloud_resources_created": 0,
        "external_gates_remaining": [
            "subscription-specific cost estimate",
            "tenant identity and network approval",
            "provider-connected plan approval",
            "external penetration and AI red-team testing",
            "formal privacy and model-risk approval",
        ],
    }
    output = ROOT / ".security-reports/preproduction-readiness.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["local_preparation_complete"]:
        raise RuntimeError("local pre-production preparation is incomplete")


if __name__ == "__main__":
    main()
