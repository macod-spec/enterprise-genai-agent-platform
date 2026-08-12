"""Release evidence configuration tests."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_performance_baseline_is_bounded_and_versioned() -> None:
    baseline = json.loads((ROOT / "config/performance-baseline.json").read_text(encoding="utf-8"))

    assert baseline["schema_version"] == 1
    assert 1 <= baseline["requests_per_sample"] <= 1_000
    assert 3 <= baseline["samples"] <= 10
    assert baseline["minimum_median_requests_per_second"] > 0
    assert 0 < baseline["maximum_failure_test_seconds"] <= 5


def test_operator_and_evaluation_guidance_is_present() -> None:
    guidance = (ROOT / "docs/evaluation-performance.md").read_text(encoding="utf-8")

    assert "not production capacity" in guidance
    assert "No real customer prompts" in guidance
    assert "make operator-demo" in guidance


def test_portfolio_pack_is_locally_reproducible_and_cloud_gated() -> None:
    overview = (ROOT / "docs/portfolio/README.md").read_text(encoding="utf-8")
    diagrams = (ROOT / "docs/portfolio/architecture-diagrams.md").read_text(encoding="utf-8")
    limitations = (ROOT / "docs/portfolio/limitations.md").read_text(encoding="utf-8")

    assert "make portfolio-evidence" in overview
    assert diagrams.count("```mermaid") == 3
    assert "has not created or claimed operation" in overview
    assert "separately approved activity" in limitations


def test_preproduction_contract_is_oidc_only_and_non_deploying() -> None:
    backend = (ROOT / "infrastructure/terraform/backend.hcl.example").read_text(encoding="utf-8")
    readiness = (ROOT / "docs/preproduction-readiness.md").read_text(encoding="utf-8")

    assert "use_oidc             = true" in backend
    assert "use_azuread_auth     = true" in backend
    assert "access_key" not in backend
    assert "must not be applied" in readiness
    assert "separately approved action" in readiness

    price_snapshot = json.loads(
        (ROOT / "config/azure-retail-price-snapshot.json").read_text(encoding="utf-8")
    )
    assert price_snapshot["priced_lower_bound_gbp"] > price_snapshot["terraform_budget_default_gbp"]
    assert price_snapshot["within_budget"] is False
