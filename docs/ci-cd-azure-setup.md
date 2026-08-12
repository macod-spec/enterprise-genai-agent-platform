# GitHub Actions → Azure OIDC federation setup (manual, one-time)

The four delivery workflows added in this stage —
`container-publish.yaml`, `terraform-plan.yaml`, `terraform-apply.yaml`,
`deploy.yaml` — are implemented, `actionlint`-clean, and structurally
correct, but **cannot authenticate to Azure until this setup is done**. That
is deliberate: creating an identity that lets automated CI act on this
subscription is a credentials/cloud-permissions decision or the platform
owner, not something to do implicitly as a side effect of writing workflow
YAML. Nothing in this document has been run by Claude; every command below
needs to be run by a human with sufficient Azure AD and subscription
permissions.

## Why OIDC, not a stored client secret

Every workflow uses `azure/login@v2` with `client-id`/`tenant-id`/
`subscription-id` only — no `client-secret`. GitHub issues a short-lived
OIDC token per workflow run; Azure AD trusts it via a **federated
credential** scoped to a specific repository and, per job, a specific
branch or a specific protected Environment. There is no long-lived Azure
credential stored in GitHub at all, so there is nothing to rotate or leak.

## 1. Create the app registration (or reuse one)

```bash
app_name="enterprise-genai-agent-platform-github-actions"
app_id="$(az ad app create --display-name "${app_name}" --query appId --output tsv)"
az ad sp create --id "${app_id}"
```

## 2. Add one federated credential per trust boundary

Each workflow job that calls `azure/login@v2` needs a federated credential
whose `subject` matches that exact job's OIDC token. Jobs behind a
protected Environment use an `environment:<name>` subject; jobs that are
not behind an Environment use a `ref:refs/heads/<branch>` subject (the
branch selected when the workflow is manually dispatched).

```bash
repo="macod-spec/enterprise-genai-agent-platform"

# Un-gated jobs (container-publish's build job needs none; terraform-apply's
# plan job authenticates to Azure before the approval gate, to plan what the
# reviewer will see — it can only ever plan, never apply).
az ad app federated-credential create --id "${app_id}" --parameters '{
  "name": "github-main-branch",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:'"${repo}"':ref:refs/heads/main",
  "audiences": ["api://AzureADTokenExchange"]
}'

# One per protected Environment used across the workflows.
for env in container-registry azure-plan azure-apply production; do
  az ad app federated-credential create --id "${app_id}" --parameters '{
    "name": "github-env-'"${env}"'",
    "issuer": "https://token.actions.githubusercontent.com",
    "subject": "repo:'"${repo}"':environment:'"${env}"'",
    "audiences": ["api://AzureADTokenExchange"]
  }'
done
```

## 3. Grant least-privilege roles (review and narrow before applying)

These are starting points, not a prescription — narrow scope further where
practical (e.g. a custom role instead of `Contributor`).

```bash
sp_object_id="$(az ad sp show --id "${app_id}" --query id --output tsv)"
subscription_id="$(az account show --query id --output tsv)"

# ACR push (container-publish.yaml)
acr_id="$(az acr show --name <your-acr-name> --query id --output tsv)"
az role assignment create --assignee "${sp_object_id}" --role AcrPush --scope "${acr_id}"

# Terraform state (terraform-plan.yaml, terraform-apply.yaml) — RBAC only,
# matching this repo's use_azuread_auth=true / shared_key_access=false state
# backend.
state_storage_id="$(az storage account show --name <your-tfstate-account> \
  --resource-group rg-novabank-ai-tfstate --query id --output tsv)"
az role assignment create --assignee "${sp_object_id}" \
  --role "Storage Blob Data Contributor" --scope "${state_storage_id}"

# Terraform plan/apply against the platform resource group. Contributor is
# broad; a custom role scoped to only the resource types this repo's modules
# create is stronger and worth doing before any real apply.
az role assignment create --assignee "${sp_object_id}" --role Contributor \
  --scope "/subscriptions/${subscription_id}/resourceGroups/<your-platform-rg>"

# AKS deploy (deploy.yaml) — cluster user role to fetch credentials, plus
# whatever in-cluster RBAC the deployed workload identity needs.
aks_id="$(az aks show --resource-group <your-platform-rg> --name <your-aks-name> \
  --query id --output tsv)"
az role assignment create --assignee "${sp_object_id}" \
  --role "Azure Kubernetes Service Cluster User Role" --scope "${aks_id}"
```

## 4. Set GitHub repository secrets and variables

```bash
gh secret set AZURE_CLIENT_ID --body "${app_id}"
gh secret set AZURE_TENANT_ID --body "$(az account show --query tenantId --output tsv)"
gh secret set AZURE_SUBSCRIPTION_ID --body "${subscription_id}"

gh variable set AZURE_STATE_STORAGE_ACCOUNT --body "<your-tfstate-account>"
gh variable set AZURE_AKS_ADMIN_GROUP_ID --body "<entra-group-id-from-bootstrap-script>"
gh variable set BUDGET_CONTACT_EMAIL --body "<your-email>"
gh variable set ACR_LOGIN_SERVER --body "<your-acr-name>.azurecr.io"
gh variable set AKS_RESOURCE_GROUP --body "<your-platform-rg>"
gh variable set AKS_CLUSTER_NAME --body "<your-aks-name>"
```

## 5. Create the protected Environments

In GitHub: **Settings → Environments** → create `container-registry`,
`azure-plan`, `azure-apply`, `production`. Add required reviewers to at
least `azure-apply` and `production` — those two can create or change real
infrastructure and deploy to it; the other two are lower-risk (a registry
push, a read-only plan) but still worth reviewing.

## What each workflow actually does once this is in place

| Workflow | Trigger | Can it change anything by itself? |
| --- | --- | --- |
| `container-publish.yaml` | `workflow_dispatch` + typed confirmation | Pushes and signs an image. No infrastructure change. |
| `terraform-plan.yaml` | `workflow_dispatch` | No — plan only, against real remote state. |
| `terraform-apply.yaml` | `workflow_dispatch` + typed confirmation + environment approval | Yes — applies exactly the plan a reviewer approved. |
| `deploy.yaml` | `workflow_dispatch` + digest input + typed confirmation + environment approval | Yes — deploys a specific, already-signed image digest to AKS. |

`deploy.yaml` additionally requires a live AKS cluster, which is currently
blocked on Azure compute quota (`docs/roadmap.md`); it will fail cleanly at
the `az aks get-credentials` step until that is resolved, which is the
correct behaviour rather than a bug to work around.
