#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
report_root="${repo_root}/.security-reports"
report_path="${report_root}/azure-aks-preflight.json"

expected_subscription="${AZURE_SUBSCRIPTION_ID:?Set AZURE_SUBSCRIPTION_ID to the approved target}"
expected_tenant="${AZURE_TENANT_ID:?Set AZURE_TENANT_ID to the approved target}"
location="${AZURE_LOCATION:-uksouth}"
aks_vm_size="${AKS_SYSTEM_NODE_VM_SIZE:-Standard_D2ns_v6}"

mkdir -p "${report_root}"

active_subscription="$(az account show --query id --output tsv)"
active_tenant="$(az account show --query tenantId --output tsv)"
if [[ "${active_subscription}" != "${expected_subscription}" || "${active_tenant}" != "${expected_tenant}" ]]; then
  echo "Active Azure account does not match the approved deployment target" >&2
  exit 1
fi

if [[ "${aks_vm_size}" == Standard_B* ]]; then
  jq -n \
    --arg subscription_id "${active_subscription}" \
    --arg tenant_id "${active_tenant}" \
    --arg location "${location}" \
    --arg aks_vm_size "${aks_vm_size}" \
    --arg reason "B-series VM sizes are refused for AKS system node pools." \
    '{subscription_id: $subscription_id, tenant_id: $tenant_id, location: $location, aks_system_node_vm_size: $aks_vm_size, passed: false, reason: $reason}' \
    > "${report_path}"
  jq . "${report_path}"
  exit 1
fi

subscription_metadata="$(az rest \
  --method get \
  --url "https://management.azure.com/subscriptions/${active_subscription}?api-version=2020-01-01")"
quota_id="$(jq -r '.subscriptionPolicies.quotaId // ""' <<< "${subscription_metadata}")"
spending_limit="$(jq -r '.subscriptionPolicies.spendingLimit // ""' <<< "${subscription_metadata}")"
usage_json="$(az vm list-usage --location "${location}" --output json)"
usage_count="$(jq 'length' <<< "${usage_json}")"
sku_json="$(az vm list-skus --location "${location}" --size "${aks_vm_size}" --all --output json)"
restricted_skus="$(jq '[.[] | select((.restrictions // []) | length > 0)] | length' <<< "${sku_json}")"
matching_skus="$(jq 'length' <<< "${sku_json}")"

passed=true
reason="AKS subscription and SKU preflight passed."
if [[ "${quota_id}" == FreeTrial* || "${spending_limit}" != "Off" ]]; then
  passed=false
  reason="Subscription still reports Free Trial quota or an active spending limit."
elif [[ "${usage_count}" == "0" ]]; then
  passed=false
  reason="Azure returned no compute quota entries for the target region."
elif [[ "${matching_skus}" == "0" || "${restricted_skus}" != "0" ]]; then
  passed=false
  reason="Requested AKS system node VM size is unavailable or restricted in the target region."
fi

jq -n \
  --arg subscription_id "${active_subscription}" \
  --arg tenant_id "${active_tenant}" \
  --arg location "${location}" \
  --arg quota_id "${quota_id}" \
  --arg spending_limit "${spending_limit}" \
  --arg aks_vm_size "${aks_vm_size}" \
  --arg reason "${reason}" \
  --argjson compute_usage_entries "${usage_count}" \
  --argjson matching_skus "${matching_skus}" \
  --argjson restricted_skus "${restricted_skus}" \
  --argjson passed "${passed}" \
  '{
    subscription_id: $subscription_id,
    tenant_id: $tenant_id,
    location: $location,
    quota_id: $quota_id,
    spending_limit: $spending_limit,
    aks_system_node_vm_size: $aks_vm_size,
    compute_usage_entries: $compute_usage_entries,
    matching_skus: $matching_skus,
    restricted_skus: $restricted_skus,
    passed: $passed,
    reason: $reason
  }' > "${report_path}"

jq . "${report_path}"
if [[ "${passed}" != "true" ]]; then
  exit 1
fi
