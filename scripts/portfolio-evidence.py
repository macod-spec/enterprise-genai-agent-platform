"""Validate that the local portfolio pack is complete and evidence-backed."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORTFOLIO = ROOT / "docs/portfolio"
REQUIRED_DOCUMENTS = {
    "README.md": ("Project statement", "Reviewer path", "Reproduce the evidence"),
    "architecture-diagrams.md": (
        "Logical platform",
        "Secure request sequence",
        "Delivery and security gates",
    ),
    "evidence-matrix.md": ("Role evidence matrix", "Honest boundary"),
    "demo-guide.md": ("Ten-minute interview", "Likely questions"),
    "limitations.md": ("Current limitations", "Mandatory production gates"),
}
REQUIRED_EVIDENCE_PATHS = (
    "src/enterprise_genai_platform/orchestration/operations.py",
    "src/enterprise_genai_platform/mcp_boundary/gateway.py",
    "src/enterprise_genai_platform/evaluation/golden_cases.json",
    "infrastructure/helm/agent-platform/Chart.yaml",
    "infrastructure/terraform/main.tf",
    ".github/workflows/ci.yaml",
    "docs/runbook.md",
    "docs/privacy-model-risk.md",
)


def main() -> None:
    checks: dict[str, bool] = {}
    for filename, markers in REQUIRED_DOCUMENTS.items():
        path = PORTFOLIO / filename
        content = path.read_text(encoding="utf-8") if path.is_file() else ""
        checks[f"document:{filename}"] = bool(content) and all(
            marker in content for marker in markers
        )

    for relative_path in REQUIRED_EVIDENCE_PATHS:
        checks[f"evidence:{relative_path}"] = (ROOT / relative_path).is_file()

    architecture = (PORTFOLIO / "architecture-diagrams.md").read_text(encoding="utf-8")
    checks["architecture:three_mermaid_diagrams"] = architecture.count("```mermaid") == 3
    limitations = (PORTFOLIO / "limitations.md").read_text(encoding="utf-8")
    checks["claims:cloud_is_explicitly_gated"] = "separately approved activity" in limitations

    report = {
        "documents_required": len(REQUIRED_DOCUMENTS),
        "evidence_paths_required": len(REQUIRED_EVIDENCE_PATHS),
        "checks": checks,
        "passed": all(checks.values()),
        "cloud_resources_created": 0,
    }
    report_path = ROOT / ".security-reports/portfolio-evidence.json"
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["passed"]:
        raise RuntimeError("portfolio evidence pack is incomplete")


if __name__ == "__main__":
    main()
