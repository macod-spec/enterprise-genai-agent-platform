#!/usr/bin/env bash
set -euo pipefail

expected_subscription="5677d45c-bce1-4375-ba74-7443b6a2a74c"
expected_tenant="04ed1ea3-6db7-4f0d-8551-cf860495341d"
location="uksouth"
state_resource_group="rg-novabank-ai-tfstate"
state_storage_account="stnovabanktf5677d45c"
state_container="tfstate"
admin_group_name="novabank-ai-aks-admins"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
report_path="${repo_root}/.security-reports/azure-prerequisites.json"

active_subscription="$(az account show --query id --output tsv)"
active_tenant="$(az account show --query tenantId --output tsv)"
if [[ "${active_subscription}" != "${expected_subscription}" || "${active_tenant}" != "${expected_tenant}" ]]; then
  echo "Active Azure subscription or tenant does not match the approved target" >&2
  exit 1
fi

providers=(
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
for provider in "${providers[@]}"; do
  az provider register --namespace "${provider}" --output none
done
signed_in_user_id="$(az ad signed-in-user show --query id --output tsv)"
admin_group_id="$(az ad group show --group "${admin_group_name}" --query id --output tsv 2>/dev/null || true)"
if [[ -z "${admin_group_id}" ]]; then
  admin_group_id="$(az ad group create \
    --display-name "${admin_group_name}" \
    --mail-nickname "novabank-ai-aks-admins" \
    --query id \
    --output tsv)"
fi
az ad group member check --group "${admin_group_id}" --member-id "${signed_in_user_id}" \
  --query value --output tsv | grep -q true || \
  az ad group member add --group "${admin_group_id}" --member-id "${signed_in_user_id}"

az group create \
  --name "${state_resource_group}" \
  --location "${location}" \
  --tags project=enterprise-genai-agent-platform purpose=terraform-state data-classification=metadata-only managed-by=bootstrap \
  --output none

if ! az storage account show --name "${state_storage_account}" --resource-group "${state_resource_group}" --output none 2>/dev/null; then
  az storage account create \
    --name "${state_storage_account}" \
    --resource-group "${state_resource_group}" \
    --location "${location}" \
    --sku Standard_LRS \
    --kind StorageV2 \
    --https-only true \
    --min-tls-version TLS1_2 \
    --allow-blob-public-access false \
    --allow-shared-key-access false \
    --default-action Deny \
    --bypass AzureServices \
    --public-network-access Enabled \
    --tags project=enterprise-genai-agent-platform purpose=terraform-state data-classification=metadata-only managed-by=bootstrap \
    --output none
fi

caller_ip="$(curl --fail --silent --show-error https://api.ipify.org)"
az storage account network-rule add \
  --resource-group "${state_resource_group}" \
  --account-name "${state_storage_account}" \
  --ip-address "${caller_ip}" \
  --output none

storage_id="$(az storage account show \
  --name "${state_storage_account}" \
  --resource-group "${state_resource_group}" \
  --query id --output tsv)"
role_exists="$(az role assignment list \
  --assignee "${signed_in_user_id}" \
  --scope "${storage_id}" \
  --role "Storage Blob Data Contributor" \
  --query 'length(@)' --output tsv)"
if [[ "${role_exists}" == "0" ]]; then
  az role assignment create \
    --assignee-object-id "${signed_in_user_id}" \
    --assignee-principal-type User \
    --scope "${storage_id}" \
    --role "Storage Blob Data Contributor" \
    --output none
fi

for attempt in {1..12}; do
  if az storage container create \
    --name "${state_container}" \
    --account-name "${state_storage_account}" \
    --auth-mode login \
    --public-access off \
    --output none 2>/dev/null; then
    break
  fi
  if [[ "${attempt}" == "12" ]]; then
    echo "Timed out waiting for Azure AD storage access" >&2
    exit 1
  fi
  sleep 5
done

mkdir -p "$(dirname "${report_path}")"
jq -n \
  --arg subscription_id "${active_subscription}" \
  --arg tenant_id "${active_tenant}" \
  --arg resource_group "${state_resource_group}" \
  --arg storage_account "${state_storage_account}" \
  --arg container "${state_container}" \
  --arg admin_group_id "${admin_group_id}" \
  --argjson providers_registered "${#providers[@]}" \
  '{
    subscription_id: $subscription_id,
    tenant_id: $tenant_id,
    provider_registrations_requested: $providers_registered,
    entra_admin_group_id: $admin_group_id,
    state_backend: {
      resource_group: $resource_group,
      storage_account: $storage_account,
      container: $container,
      azure_ad_auth: true,
      shared_key_access: false,
      public_blob_access: false,
      network_default_deny: true
    },
    main_platform_resources_created: 0,
    terraform_apply_used: false,
    passed: true
  }' > "${report_path}"
jq . "${report_path}"
