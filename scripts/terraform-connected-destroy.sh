#!/usr/bin/env bash
set -euo pipefail

readonly REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly TERRAFORM_ROOT="${REPO_ROOT}/infrastructure/terraform"
readonly REPORT_ROOT="${REPO_ROOT}/.security-reports"
readonly PREREQUISITE_REPORT="${REPORT_ROOT}/azure-prerequisites.json"
readonly EXPECTED_SUBSCRIPTION="5677d45c-bce1-4375-ba74-7443b6a2a74c"
readonly EXPECTED_TENANT="04ed1ea3-6db7-4f0d-8551-cf860495341d"
readonly PLATFORM_RESOURCE_GROUP="rg-novabank-ai-dev"
readonly REQUIRED_CONFIRMATION="DELETE_${PLATFORM_RESOURCE_GROUP}"
readonly TEMPORARY_ROOT="$(mktemp -d)"
trap 'rm -rf -- "${TEMPORARY_ROOT}"' EXIT

for tool in az jq terraform; do
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "Required tool is unavailable: ${tool}" >&2
    exit 1
  fi
done

if [[ ! -f "${PREREQUISITE_REPORT}" ]]; then
  echo "Azure prerequisite evidence is missing: ${PREREQUISITE_REPORT}" >&2
  exit 1
fi

active_subscription="$(az account show --query id --output tsv)"
active_tenant="$(az account show --query tenantId --output tsv)"
if [[ "${active_subscription}" != "${EXPECTED_SUBSCRIPTION}" || "${active_tenant}" != "${EXPECTED_TENANT}" ]]; then
  echo "Destroy refused: active Azure account is not the approved target" >&2
  exit 1
fi

state_resource_group="$(jq -er '.state_backend.resource_group' "${PREREQUISITE_REPORT}")"
state_storage_account="$(jq -er '.state_backend.storage_account' "${PREREQUISITE_REPORT}")"
state_container="$(jq -er '.state_backend.container' "${PREREQUISITE_REPORT}")"
admin_group_id="$(jq -er '.entra_admin_group_id' "${PREREQUISITE_REPORT}")"

terraform -chdir="${TERRAFORM_ROOT}" init -reconfigure -input=false \
  -backend-config="resource_group_name=${state_resource_group}" \
  -backend-config="storage_account_name=${state_storage_account}" \
  -backend-config="container_name=${state_container}" \
  -backend-config="key=enterprise-genai-agent-platform/dev.tfstate" \
  -backend-config="use_azuread_auth=true" \
  -backend-config="use_cli=true"
terraform -chdir="${TERRAFORM_ROOT}" validate

deployment_confirmation="I_ACCEPT_AZURE_COSTS" # pragma: allowlist secret
terraform -chdir="${TERRAFORM_ROOT}" plan -destroy -lock=true -input=false \
  -var="subscription_id=${active_subscription}" \
  -var='enable_deployment=true' \
  -var="deployment_confirmation=${deployment_confirmation}" \
  -var="aks_admin_group_object_ids=[\"${admin_group_id}\"]" \
  -var='budget_contact_emails=["mcleonard.od@outlook.com"]' \
  -out="${TEMPORARY_ROOT}/destroy.tfplan"

terraform -chdir="${TERRAFORM_ROOT}" show -json "${TEMPORARY_ROOT}/destroy.tfplan" \
  >"${TEMPORARY_ROOT}/destroy-plan.json"
delete_count="$(jq '[.resource_changes[]? | select(.change.actions | index("delete"))] | length' "${TEMPORARY_ROOT}/destroy-plan.json")"
create_count="$(jq '[.resource_changes[]? | select(.change.actions | index("create"))] | length' "${TEMPORARY_ROOT}/destroy-plan.json")"
if [[ "${delete_count}" == "0" || "${create_count}" != "0" ]]; then
  echo "Destroy refused: expected deletes and no creates; got ${delete_count} deletes and ${create_count} creates" >&2
  exit 1
fi

if [[ "${DESTROY_DRY_RUN:-0}" == "1" ]]; then
  echo "Dry run passed: Terraform planned ${delete_count} deletions and zero creations."
  echo "The state backend resource group ${state_resource_group} is deliberately preserved."
  exit 0
fi

if [[ "${DESTROY_CONFIRMATION:-}" != "${REQUIRED_CONFIRMATION}" ]]; then
  echo "Destroy plan is valid, but no resources were deleted." >&2
  echo "To execute it, set DESTROY_CONFIRMATION=${REQUIRED_CONFIRMATION} and run make destroy." >&2
  exit 1
fi

terraform -chdir="${TERRAFORM_ROOT}" apply -input=false -auto-approve "${TEMPORARY_ROOT}/destroy.tfplan"

if az group exists --name "${PLATFORM_RESOURCE_GROUP}" | grep -qx true; then
  echo "Destroy failed: ${PLATFORM_RESOURCE_GROUP} still exists" >&2
  exit 1
fi

echo "Platform resource group deleted. Terraform state backend ${state_resource_group} was preserved."
