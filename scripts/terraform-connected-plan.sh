#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
terraform_root="${repo_root}/infrastructure/terraform"
report_root="${repo_root}/.security-reports"
prerequisite_report="${report_root}/azure-prerequisites.json"
temporary_root="$(mktemp -d)"
trap 'rm -rf -- "${temporary_root}"' EXIT

expected_subscription="${AZURE_SUBSCRIPTION_ID:?Set AZURE_SUBSCRIPTION_ID to the approved target}"
active_subscription="$(az account show --query id --output tsv)"
if [[ "${active_subscription}" != "${expected_subscription}" ]]; then
  echo "Active subscription does not match the approved connected-plan target" >&2
  exit 1
fi
if [[ ! -f "${prerequisite_report}" ]]; then
  echo "Azure prerequisite evidence is missing" >&2
  exit 1
fi

required_providers=(
  Microsoft.Cache
  Microsoft.CognitiveServices
  Microsoft.ContainerRegistry
  Microsoft.ContainerService
  Microsoft.DBforPostgreSQL
  Microsoft.Insights
  Microsoft.KeyVault
  Microsoft.Network
  Microsoft.ManagedIdentity
  Microsoft.OperationalInsights
  Microsoft.Search
  Microsoft.Storage
)
for provider in "${required_providers[@]}"; do
  state="$(az provider show --namespace "${provider}" --query registrationState --output tsv)"
  if [[ "${state}" != "Registered" ]]; then
    echo "Provider ${provider} is not fully registered" >&2
    exit 1
  fi
done

state_resource_group="$(jq -r '.state_backend.resource_group' "${prerequisite_report}")"
state_storage_account="$(jq -r '.state_backend.storage_account' "${prerequisite_report}")"
state_container="$(jq -r '.state_backend.container' "${prerequisite_report}")"
admin_group_id="$(jq -r '.entra_admin_group_id' "${prerequisite_report}")"
deployment_confirmation="I_ACCEPT_AZURE_COSTS" # pragma: allowlist secret

terraform -chdir="${terraform_root}" init \
  -reconfigure \
  -input=false \
  -backend-config="resource_group_name=${state_resource_group}" \
  -backend-config="storage_account_name=${state_storage_account}" \
  -backend-config="container_name=${state_container}" \
  -backend-config="key=enterprise-genai-agent-platform/dev.tfstate" \
  -backend-config="use_azuread_auth=true" \
  -backend-config="use_cli=true"
terraform -chdir="${terraform_root}" validate

set +e
terraform -chdir="${terraform_root}" plan \
  -refresh=false \
  -lock=true \
  -input=false \
  -detailed-exitcode \
  -var="subscription_id=${active_subscription}" \
  -var='enable_deployment=true' \
  -var="deployment_confirmation=${deployment_confirmation}" \
  -var="aks_admin_group_object_ids=[\"${admin_group_id}\"]" \
  -var='budget_contact_emails=["mcleonard.od@outlook.com"]' \
  -out="${temporary_root}/connected.tfplan" \
  > "${temporary_root}/plan.log" 2>&1
plan_exit=$?
set -e
if [[ "${plan_exit}" != "2" ]]; then
  tail -100 "${temporary_root}/plan.log" >&2
  echo "Expected a non-empty plan (exit 2), received ${plan_exit}" >&2
  exit 1
fi

terraform -chdir="${terraform_root}" show -json \
  "${temporary_root}/connected.tfplan" > "${temporary_root}/connected-plan.json"
create_count="$(jq '[.resource_changes[]? | select(.change.actions == ["create"])] | length' "${temporary_root}/connected-plan.json")"
other_change_count="$(jq '[.resource_changes[]? | select(.change.actions != ["create"] and .change.actions != ["no-op"])] | length' "${temporary_root}/connected-plan.json")"
if [[ "${create_count}" == "0" || "${other_change_count}" != "0" ]]; then
  echo "Connected plan did not contain the expected create-only change set" >&2
  exit 1
fi

jq -n \
  --arg subscription_id "${active_subscription}" \
  --argjson creates "${create_count}" \
  --argjson other_changes "${other_change_count}" \
  '{
    mode: "provider-connected-non-zero-plan",
    subscription_id: $subscription_id,
    planned_creates: $creates,
    planned_non_create_changes: $other_changes,
    remote_state_used: true,
    provider_auto_registration: false,
    plan_artifact_retained: false,
    terraform_apply_used: false,
    main_platform_resources_created: 0,
    passed: ($creates > 0 and $other_changes == 0)
  }' > "${report_root}/terraform-connected-plan-summary.json"
jq . "${report_root}/terraform-connected-plan-summary.json"
