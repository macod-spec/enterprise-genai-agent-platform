"""Tests for repository-level security invariants."""

import re
import tomllib
from pathlib import Path

from enterprise_genai_platform import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_package_has_a_version() -> None:
    """Build and audit tooling must be able to identify the package version."""
    assert __version__ == "0.1.0"


def test_local_secret_files_are_gitignored() -> None:
    """Local secret-bearing files must not be eligible for a commit."""
    ignored_patterns = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert ".env" in ignored_patterns
    assert ".env.local" in ignored_patterns


def test_example_environment_contains_no_secret_fields() -> None:
    """The committed example must contain only explicitly safe local settings."""
    allowed_keys = {
        "API_PREFIX",
        "APP_ENV",
        "APP_NAME",
        "AZURE_STATE_STORAGE_ACCOUNT",
        "AZURE_SUBSCRIPTION_ID",
        "AZURE_TENANT_ID",
        "CORS_ALLOWED_ORIGINS",
        "GRAFANA_ADMIN_PASSWORD",
        "LOG_LEVEL",
        "MAX_REQUEST_BODY_BYTES",
        "MAX_WORKFLOW_STEPS",
        "METRICS_ENABLED",
        "MCP_MAX_ATTEMPTS",
        "MCP_RATE_LIMIT",
        "MCP_RATE_WINDOW_SECONDS",
        "MCP_TOOL_TIMEOUT_SECONDS",
        "MODEL_PROVIDER",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORT_ENABLED",
        "POSTGRES_PASSWORD",
        "RATE_LIMIT_REQUESTS",
        "RATE_LIMIT_WINDOW_SECONDS",
        "REQUEST_TIMEOUT_SECONDS",
        "REDIS_PASSWORD",
        "STATE_BACKEND",
        "STATE_CONNECTION_URL",
        "STATE_DATABASE_PATH",
    }
    configured_values = {
        line.split("=", maxsplit=1)[0]: line.split("=", maxsplit=1)[1]
        for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    }

    assert configured_values.keys() <= allowed_keys
    assert configured_values["AZURE_SUBSCRIPTION_ID"] == ""
    assert configured_values["AZURE_TENANT_ID"] == ""
    assert configured_values["AZURE_STATE_STORAGE_ACCOUNT"] == ""
    assert all(
        not value
        for key, value in configured_values.items()
        if any(marker in key for marker in ("PASSWORD", "SECRET", "TOKEN", "KEY"))
    )


def test_dependency_lock_is_hash_bearing_and_current() -> None:
    """The committed lock must contain artifact hashes and match project metadata."""
    lock_text = (ROOT / "uv.lock").read_text(encoding="utf-8")

    assert "revision = 3" in lock_text
    assert 'hash = "sha256:' in lock_text
    assert 'name = "enterprise-genai-agent-platform"' in lock_text
    assert 'name = "msgpack"' in lock_text
    assert 'version = "1.2.1"' in lock_text


def test_project_license_and_local_sast_policy_are_declared() -> None:
    """License and local SAST controls must remain reviewable repository assets."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    semgrep = (ROOT / ".semgrep.yml").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yaml").read_text(encoding="utf-8")

    assert project["project"]["license"] == "MIT"
    assert (ROOT / "LICENSE").is_file()
    assert "python-dangerous-eval" in semgrep
    assert "--metrics off" in workflow
    assert "@master" not in workflow


def test_helm_defaults_require_digest_pinned_images() -> None:
    """Production values must fail closed while kind uses an explicit local mode."""
    production_values = (ROOT / "infrastructure/helm/agent-platform/values.yaml").read_text(
        encoding="utf-8"
    )
    kind_values = (ROOT / "infrastructure/helm/agent-platform/values-kind.yaml").read_text(
        encoding="utf-8"
    )
    deployment = (ROOT / "infrastructure/helm/agent-platform/templates/deployment.yaml").read_text(
        encoding="utf-8"
    )

    assert "localDevelopment:\n  enabled: false" in production_values
    assert "digest: sha256:" in production_values
    assert "localDevelopment:\n  enabled: true" in kind_values
    assert "pullPolicy: Never" in kind_values
    assert 'fail "image.digest is required' in deployment


def test_local_image_signing_is_isolated_and_keyless_at_rest() -> None:
    """Signing must be offline, pinned and destroy its ephemeral private key."""
    signing_script = (ROOT / "scripts/sign-local-image.sh").read_text(encoding="utf-8")

    assert "gcr.io/projectsigstore/cosign@sha256:" in signing_script
    assert "--network none" in signing_script
    assert "/var/run/docker.sock" not in signing_script
    assert "trap cleanup EXIT" in signing_script


def test_kind_integration_enforces_security_and_cleanup() -> None:
    """The disposable cluster must enforce restricted PSS and always be deleted."""
    kind_script = (ROOT / "scripts/kind-integration.sh").read_text(encoding="utf-8")

    assert "pod-security.kubernetes.io/enforce=restricted" in kind_script
    assert "kind delete cluster" in kind_script
    assert "trap cleanup EXIT" in kind_script
    assert "allowPrivilegeEscalation == false" in kind_script
    assert 'kind-metrics.prom"' in kind_script
    assert "curl --fail --silent http://127.0.0.1:18001/metrics | grep -q" not in kind_script


def test_codeql_uploads_and_retains_results() -> None:
    """Public-repository CodeQL must upload findings and retain review evidence."""
    workflow = (ROOT / ".github/workflows/codeql.yaml").read_text(encoding="utf-8")

    assert "actions: read" in workflow
    assert "contents: read" in workflow
    assert "security-events: write" in workflow
    assert "upload: true" in workflow
    assert "name: codeql-sarif" in workflow
    assert "if-no-files-found: error" in workflow


def test_destroy_is_account_locked_reviewed_and_never_automatic() -> None:
    """Teardown must require an exact target, reviewed plan and confirmation."""
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    destroy = (ROOT / "scripts/terraform-connected-destroy.sh").read_text(encoding="utf-8")

    assert "destroy:" in makefile
    assert "AZURE_SUBSCRIPTION_ID:?" in destroy
    assert "AZURE_TENANT_ID:?" in destroy
    assert 'REQUIRED_CONFIRMATION="DELETE_${PLATFORM_RESOURCE_GROUP}"' in destroy
    assert "plan -destroy" in destroy
    assert '"${create_count}" != "0"' in destroy
    assert "DESTROY_DRY_RUN:-0" in destroy
    assert "apply -input=false -auto-approve" in destroy


def test_environment_age_guard_warns_without_cloud_credentials() -> None:
    """The hourly cost guard must use a non-secret timestamp and deduplicate alerts."""
    workflow = (ROOT / ".github/workflows/environment-age.yaml").read_text(encoding="utf-8")

    assert 'cron: "17 * * * *"' in workflow
    assert "AZURE_ENV_CREATED_AT" in workflow
    assert "PYTHONPATH: src" in workflow
    assert "issues: write" in workflow
    assert "gh issue list --state open" in workflow
    assert "az login" not in workflow


def test_durable_state_waits_for_authenticated_connectivity() -> None:
    """Container health must be followed by bounded host-side connection retries."""
    verifier = (ROOT / "scripts/verify-durable-state.py").read_text(encoding="utf-8")

    assert "def wait_until_connectable" in verifier
    assert "attempts: int = 10" in verifier
    assert "time.sleep(1)" in verifier


def test_terraform_default_plan_is_cost_locked_and_non_deploying() -> None:
    """Every Azure lookup and resource must be absent from the default plan."""
    main = (ROOT / "infrastructure/terraform/main.tf").read_text(encoding="utf-8")
    variables = (ROOT / "infrastructure/terraform/variables.tf").read_text(encoding="utf-8")
    plan_script = (ROOT / "scripts/terraform-plan-zero.sh").read_text(encoding="utf-8")
    zero_plan_test = (
        ROOT / "infrastructure/terraform/terraform-tests/zero-plan.tftest.hcl"
    ).read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yaml").read_text(encoding="utf-8")

    resource_blocks = re.findall(r'resource "azurerm_[^}]+}', main, flags=re.DOTALL)
    assert resource_blocks
    assert all(re.search(r"count\s*=\s*local\.deploy", block) for block in resource_blocks)
    assert 'data "azurerm_client_config" "current" {\n  count = local.deploy' in main
    assert "default     = false" in variables
    assert 'mock_provider "azurerm"' in zero_plan_test
    assert "command = plan" in zero_plan_test
    assert "enable_deployment = false" in zero_plan_test
    assert "resource_changes}" in plan_script
    assert "terraform apply" not in plan_script
    assert "terraform-zero-resource-plan" in workflow
    assert "az login" not in workflow


def test_azure_modules_use_private_identity_and_cost_controls() -> None:
    module_root = ROOT / "infrastructure/terraform/modules"
    compute = (module_root / "compute/main.tf").read_text(encoding="utf-8")
    compute_variables = (module_root / "compute/variables.tf").read_text(encoding="utf-8")
    data = (module_root / "data/main.tf").read_text(encoding="utf-8")
    ai = (module_root / "ai/main.tf").read_text(encoding="utf-8")
    governance = (module_root / "governance/main.tf").read_text(encoding="utf-8")
    root = (ROOT / "infrastructure/terraform/main.tf").read_text(encoding="utf-8")
    root_variables = (ROOT / "infrastructure/terraform/variables.tf").read_text(encoding="utf-8")
    apply_script = (ROOT / "scripts/terraform-connected-apply.sh").read_text(encoding="utf-8")
    aks_preflight = (ROOT / "scripts/azure-aks-preflight.sh").read_text(encoding="utf-8")
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    assert re.search(r"private_cluster_enabled\s*=\s*true", compute)
    assert re.search(r"local_account_disabled\s*=\s*true", compute)
    assert re.search(r"workload_identity_enabled\s*=\s*true", compute)
    assert "vm_size                      = var.system_node_vm_size" in compute
    assert "node_count                   = var.system_node_count" in compute
    assert 'variable "system_node_vm_size"' in compute_variables
    assert 'variable "aks_system_node_vm_size"' in root_variables
    assert '!can(regex("^Standard_B", var.aks_system_node_vm_size))' in root_variables
    assert '"${repo_root}/scripts/azure-aks-preflight.sh"' in apply_script
    assert (
        '-var="aks_system_node_vm_size=${AKS_SYSTEM_NODE_VM_SIZE:-Standard_D2s_v5}"' in apply_script
    )
    assert "FreeTrial*" in aks_preflight
    assert 'spending_limit}" != "Off"' in aks_preflight
    assert 'az vm list-usage --location "${location}"' in aks_preflight
    assert 'az vm list-skus --location "${location}" --size "${aks_vm_size}"' in aks_preflight
    assert '[[ "${aks_vm_size}" == Standard_B* ]]' in aks_preflight
    assert "azure-aks-preflight:" in makefile
    assert re.search(r"public_network_access_enabled\s*=\s*false", data)
    assert re.search(r'public_network_access\s*=\s*"Disabled"', data)
    assert re.search(r"access_keys_authentication_enabled\s*=\s*false", data)
    assert re.search(r"password_auth_enabled\s*=\s*false", data)
    assert len(re.findall(r"public_network_access_enabled\s*=\s*false", ai)) == 2
    assert "local_auth_enabled" in ai and "local_authentication_enabled" in ai
    assert re.search(r"local_authentication_enabled\s*=\s*false", governance)
    assert governance.count("notification {") == 3
    module_blocks = re.findall(r'module "[^}]+}', root, flags=re.DOTALL)
    assert module_blocks
    assert all(re.search(r"count\s*=\s*local\.deploy", block) for block in module_blocks)
