#!/usr/bin/env bash
# Stand up (or idempotently reconcile) the Azure Container Apps demo endpoint.
# Demo-only, per docs/cost-tiers.md: not part of the Terraform-managed platform,
# scales to zero when idle, and is expected to be torn down with aca-down.sh
# between demo sessions.
set -euo pipefail

resource_group="${ACA_RESOURCE_GROUP:-rg-novabank-ai-dev}"
environment_name="${ACA_ENVIRONMENT_NAME:-nova-aca-env}"
app_name="${ACA_APP_NAME:-nova-gateway}"
location="${ACA_LOCATION:-uksouth}"
law_name="${ACA_LOG_ANALYTICS_WORKSPACE:-log-novabank-ai-dev}"
acr_name="${ACA_ACR_NAME:-acrnovabankaidev}"
image_digest="${ACA_IMAGE_DIGEST:?Set ACA_IMAGE_DIGEST to a real sha256: digest from container-publish.yaml}"
openai_account="${ACA_OPENAI_ACCOUNT:-oai-novabank-ai-dev}"
search_service="${ACA_SEARCH_SERVICE:-srch-novabank-ai-dev}"
content_safety_account="${ACA_CONTENT_SAFETY_ACCOUNT:-cs-novabank-ai-dev}"
model_deployment="${ACA_MODEL_DEPLOYMENT:-gpt-5-nano}"
daily_budget_gbp="${ACA_DAILY_BUDGET_GBP:-2.0}"

az provider register --namespace Microsoft.App --wait
az provider register --namespace Microsoft.OperationalInsights --wait
az extension add --name containerapp --upgrade --yes >/dev/null

law_id="$(az monitor log-analytics workspace show --resource-group "${resource_group}" --workspace-name "${law_name}" --query customerId --output tsv)"
law_key="$(az monitor log-analytics workspace get-shared-keys --resource-group "${resource_group}" --workspace-name "${law_name}" --query primarySharedKey --output tsv)"

az containerapp env show --name "${environment_name}" --resource-group "${resource_group}" >/dev/null 2>&1 || \
  az containerapp env create \
    --name "${environment_name}" \
    --resource-group "${resource_group}" \
    --location "${location}" \
    --logs-destination log-analytics \
    --logs-workspace-id "${law_id}" \
    --logs-workspace-key "${law_key}"

# Note: APP_ENV=local is required, not a shortcut. The gateway's local
# identity headers (X-Local-User/X-Local-Roles) are the only auth mechanism
# implemented; any other app_env makes every authenticated route return 503
# (docs/portfolio/live-verification.md, gateway/auth.py). Every agent
# endpoint returns 401 without them — that authentication requirement, not
# an IP allowlist, is the deployment's actual access control (a rotating
# home IP is unsuitable for that role and was deliberately dropped: it adds
# an operational-leak surface for no real security benefit over the
# gateway's own auth). The per-tenant token budget below is the other
# control doing real work — it caps blast radius even for an authenticated
# caller.
az containerapp create \
  --name "${app_name}" \
  --resource-group "${resource_group}" \
  --environment "${environment_name}" \
  --image "${acr_name}.azurecr.io/enterprise-agent-platform@${image_digest}" \
  --registry-server "${acr_name}.azurecr.io" \
  --registry-identity system \
  --target-port 8000 \
  --ingress external \
  --system-assigned \
  --min-replicas 0 \
  --max-replicas 2 \
  --cpu 0.5 --memory 1.0Gi \
  --env-vars \
    APP_ENV=local \
    MODEL_GATEWAY_PROVIDER=azure_openai \
    "MODEL_GATEWAY_ALLOWLIST=[\"${model_deployment}\"]" \
    "MODEL_GATEWAY_DAILY_BUDGET_GBP=${daily_budget_gbp}" \
    "AZURE_OPENAI_ENDPOINT=https://${openai_account}.openai.azure.com/" \
    CONTENT_SAFETY_PROVIDER=azure \
    "CONTENT_SAFETY_ENDPOINT=https://${content_safety_account}.cognitiveservices.azure.com/" \
    RAG_PROVIDER=azure_search \
    "AZURE_SEARCH_ENDPOINT=https://${search_service}.search.windows.net" \
    "RAG_SYNTHESIS_MODEL=${model_deployment}" \
  --revision-suffix reconcile

principal_id="$(az containerapp show --name "${app_name}" --resource-group "${resource_group}" --query identity.principalId --output tsv)"
acr_id="$(az acr show --name "${acr_name}" --query id --output tsv)"
oai_id="$(az cognitiveservices account show --name "${openai_account}" --resource-group "${resource_group}" --query id --output tsv)"
search_id="$(az search service show --name "${search_service}" --resource-group "${resource_group}" --query id --output tsv)"
cs_id="$(az cognitiveservices account show --name "${content_safety_account}" --resource-group "${resource_group}" --query id --output tsv)"

for role_scope in \
  "AcrPull ${acr_id}" \
  "Cognitive Services OpenAI User ${oai_id}" \
  "Search Index Data Reader ${search_id}" \
  "Cognitive Services User ${cs_id}"; do
  role="${role_scope% *}"
  scope="${role_scope##* }"
  az role assignment create --assignee-object-id "${principal_id}" --assignee-principal-type ServicePrincipal \
    --role "${role}" --scope "${scope}" --output none 2>/dev/null || true
done

# No IP allowlist: a home IP rotates every few weeks (breaking access and
# requiring the real IP to be documented somewhere, which is its own leak
# surface) and adds no real control beyond what gateway auth already
# enforces. Reconcile away any restriction left by an older run.
az containerapp ingress access-restriction remove \
  --name "${app_name}" --resource-group "${resource_group}" \
  --rule-name my-ip --output none 2>/dev/null || true

fqdn="$(az containerapp show --name "${app_name}" --resource-group "${resource_group}" --query properties.configuration.ingress.fqdn --output tsv)"
echo "https://${fqdn}"
