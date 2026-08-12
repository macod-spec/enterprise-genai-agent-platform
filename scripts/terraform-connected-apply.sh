#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
terraform_root="${repo_root}/infrastructure/terraform"
report_root="${repo_root}/.security-reports"
prerequisite_report="${report_root}/azure-prerequisites.json"
temporary_root="$(mktemp -d)"
trap 'rm -rf -- "${temporary_root}"' EXIT

expected_subscription="${AZURE_SUBSCRIPTION_ID:?Set AZURE_SUBSCRIPTION_ID to the approved target}"
expected_tenant="${AZURE_TENANT_ID:?Set AZURE_TENANT_ID to the approved target}"
active_subscription="$(az account show --query id --output tsv)"
active_tenant="$(az account show --query tenantId --output tsv)"
if [[ "${active_subscription}" != "${expected_subscription}" || "${active_tenant}" != "${expected_tenant}" ]]; then
  echo "Active Azure account does not match the approved deployment target" >&2
  exit 1
fi
if [[ ! -f "${prerequisite_report}" ]]; then
  echo "Azure prerequisite evidence is missing" >&2
  exit 1
fi

"${repo_root}/scripts/azure-aks-preflight.sh"

state_resource_group="$(jq -r '.state_backend.resource_group' "${prerequisite_report}")"
state_storage_account="$(jq -r '.state_backend.storage_account' "${prerequisite_report}")"
state_container="$(jq -r '.state_backend.container' "${prerequisite_report}")"
admin_group_id="$(jq -r '.entra_admin_group_id' "${prerequisite_report}")"
deployment_confirmation="I_ACCEPT_AZURE_COSTS" # pragma: allowlist secret

terraform -chdir="${terraform_root}" init -reconfigure -input=false \
  -backend-config="resource_group_name=${state_resource_group}" \
  -backend-config="storage_account_name=${state_storage_account}" \
  -backend-config="container_name=${state_container}" \
  -backend-config="key=enterprise-genai-agent-platform/dev.tfstate" \
  -backend-config="use_azuread_auth=true" \
  -backend-config="use_cli=true"
terraform -chdir="${terraform_root}" validate

terraform -chdir="${terraform_root}" plan -lock=true -input=false \
  -var="subscription_id=${active_subscription}" \
  -var='enable_deployment=true' \
  -var="deployment_confirmation=${deployment_confirmation}" \
  -var="aks_admin_group_object_ids=[\"${admin_group_id}\"]" \
  -var="aks_system_node_vm_size=${AKS_SYSTEM_NODE_VM_SIZE:-Standard_D2ns_v6}" \
  -var='budget_contact_emails=["mcleonard.od@outlook.com"]' \
  -out="${temporary_root}/approved.tfplan"

terraform -chdir="${terraform_root}" show -json "${temporary_root}/approved.tfplan" > "${temporary_root}/approved-plan.json"
create_count="$(jq '[.resource_changes[]? | select(.change.actions == ["create"])] | length' "${temporary_root}/approved-plan.json")"
unsafe_count="$(jq '[.resource_changes[]? | select((.change.actions | index("delete")) != null)] | length' "${temporary_root}/approved-plan.json")"
if [[ "${create_count}" -lt 1 || "${create_count}" -gt 50 || "${unsafe_count}" != "0" ]]; then
  echo "Apply refused: expected 1-50 creates and no deletes; got ${create_count} creates and ${unsafe_count} deletes" >&2
  exit 1
fi

terraform -chdir="${terraform_root}" apply -input=false -auto-approve "${temporary_root}/approved.tfplan"

jq -n --arg subscription_id "${active_subscription}" --argjson creates "${create_count}" \
  '{subscription_id: $subscription_id, applied_planned_creates: $creates, terraform_apply_used: true, passed: true}' \
  > "${report_root}/terraform-connected-apply-summary.json"
jq . "${report_root}/terraform-connected-apply-summary.json"
