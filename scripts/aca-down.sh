#!/usr/bin/env bash
# Tear down the Azure Container Apps demo endpoint. Deletes only the app and
# its environment (demo-only, per docs/cost-tiers.md) — ACR, Azure OpenAI,
# AI Search and Content Safety are managed elsewhere and untouched.
set -euo pipefail

resource_group="${ACA_RESOURCE_GROUP:-rg-novabank-ai-dev}"
environment_name="${ACA_ENVIRONMENT_NAME:-nova-aca-env}"
app_name="${ACA_APP_NAME:-nova-gateway}"

az containerapp show --name "${app_name}" --resource-group "${resource_group}" >/dev/null 2>&1 && \
  az containerapp delete --name "${app_name}" --resource-group "${resource_group}" --yes

az containerapp env show --name "${environment_name}" --resource-group "${resource_group}" >/dev/null 2>&1 && \
  az containerapp env delete --name "${environment_name}" --resource-group "${resource_group}" --yes

echo "Container Apps demo endpoint removed."
