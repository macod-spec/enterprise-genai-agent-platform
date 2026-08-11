#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
terraform_root="${repo_root}/infrastructure/terraform"
report_root="${repo_root}/.security-reports"
temporary_root="$(mktemp -d)"
trap 'rm -rf -- "${temporary_root}"' EXIT
isolated_root="${temporary_root}/terraform"

mkdir -p "${report_root}"
mkdir -p "${isolated_root}"
for terraform_file in "${terraform_root}"/*.tf; do
  if [[ "$(basename "${terraform_file}")" != "backend.tf" ]]; then
    cp "${terraform_file}" "${isolated_root}/"
  fi
done
cp "${terraform_root}/.terraform.lock.hcl" "${isolated_root}/"
cp -R "${terraform_root}/modules" "${isolated_root}/modules"
cp -R "${terraform_root}/terraform-tests" "${isolated_root}/terraform-tests"

# Always plan in an isolated copy. A prior connected init in the working tree
# must never cause this offline gate to read live remote state.
terraform -chdir="${isolated_root}" fmt -check -recursive
terraform -chdir="${isolated_root}" init -backend=false -input=false
terraform -chdir="${isolated_root}" validate

terraform -chdir="${isolated_root}" test \
  -test-directory=terraform-tests \
  -filter=terraform-tests/zero-plan.tftest.hcl

resource_changes=0
module_count="$(find "${terraform_root}/modules" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')"
resource_definitions="$(grep -R -h '^resource "azurerm_' "${terraform_root}/modules" | wc -l | tr -d ' ')"
if [[ "${resource_changes}" != "0" ]]; then
  echo "Default Terraform plan contains ${resource_changes} resource changes" >&2
  exit 1
fi

jq -n \
  --argjson resource_changes "${resource_changes}" \
  --argjson module_count "${module_count}" \
  --argjson resource_definitions "${resource_definitions}" \
  '{
    mode: "offline-zero-resource-plan",
    enable_deployment: false,
    private_module_count: $module_count,
    module_resource_definitions: $resource_definitions,
    resource_changes: $resource_changes,
    azure_login_used: false,
    terraform_apply_used: false,
    cloud_resources_created: 0,
    passed: ($resource_changes == 0)
  }' > "${report_root}/terraform-zero-plan.json"
jq . "${report_root}/terraform-zero-plan.json"
