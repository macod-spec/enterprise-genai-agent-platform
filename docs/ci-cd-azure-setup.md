# GitHub Actions → Azure OIDC federation setup (one-time)

Status: **done and live-verified** (2026-08-12), with explicit approval at
each consequential step (identity creation, role grants, storage firewall
change). `terraform-plan.yaml` has successfully authenticated via OIDC,
initialized against real remote state, and produced a real connected plan
(5 to add, 2 to change, 0 to destroy — AKS, managed Redis, workload identity
federation and an ACR-pull role assignment, i.e. exactly what was behind the
zero-resource deployment lock). This document is kept as the reference for
what was done and, if the identity ever needs to be recreated, exactly how.

## Two real problems found only by running it live

1. **GitHub's OIDC subject claim uses an "immutable ID" format**,
   `repo:<owner>@<owner_id>/<repo>@<repo_id>:...`, not the classic
   `repo:<owner>/<repo>:...` this document originally assumed. The first
   live run failed with `AADSTS700213: No matching federated identity
   record found`. Fixed by rebuilding every federated credential's
   `subject` with the numeric owner/repo IDs (`gh api user` /
   `gh api repos/<owner>/<repo>` to get them). The federated-credential
   commands below already reflect the corrected format.
2. **The Terraform state storage account's firewall (`defaultAction: Deny`,
   one allowed IP) unconditionally blocks GitHub-hosted runners** — their
   IP pool has no fixed range Azure's 200-rule-per-account IP allowlist
   could hold (GitHub currently publishes 7,280 CIDR ranges for Actions).
   Resolved, with explicit sign-off, by setting the storage account's
   `defaultAction` to `Allow`; `allowSharedKeyAccess` remains `false`, so
   Azure AD auth (OIDC-federated identity, RBAC-scoped) is still the only
   way in — this removes network-layer defense in depth, not the identity
   gate. The alternative (a self-hosted runner inside the private network)
   is architecturally what a real bank would do, but is out of scope here.

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

**GitHub's actual subject format includes numeric owner/repo IDs**,
`repo:<owner>@<owner_id>/<repo>@<repo_id>:...` — not the plain
`repo:<owner>/<repo>:...` shown in GitHub's own OIDC docs and in most
examples online. Get the IDs first:

```bash
owner_id="$(gh api user --jq .id)"
repo_id="$(gh api repos/macod-spec/enterprise-genai-agent-platform --jq .id)"
owner_repo="macod-spec@${owner_id}/enterprise-genai-agent-platform@${repo_id}"
```

```bash
# Un-gated jobs (container-publish's build job needs none; terraform-apply's
# plan job authenticates to Azure before the approval gate, to plan what the
# reviewer will see — it can only ever plan, never apply).
az ad app federated-credential create --id "${app_id}" --parameters '{
  "name": "github-main-branch",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:'"${owner_repo}"':ref:refs/heads/main",
  "audiences": ["api://AzureADTokenExchange"]
}'

# One per protected Environment used across the workflows.
for env in container-registry azure-plan azure-apply production; do
  az ad app federated-credential create --id "${app_id}" --parameters '{
    "name": "github-env-'"${env}"'",
    "issuer": "https://token.actions.githubusercontent.com",
    "subject": "repo:'"${owner_repo}"':environment:'"${env}"'",
    "audiences": ["api://AzureADTokenExchange"]
  }'
done
```

If a live run ever fails with `AADSTS700213: No matching federated identity
record found`, the failure log prints the exact `subject claim` GitHub
actually sent — compare it against `az ad app federated-credential list
--id "${app_id}"` rather than re-guessing the format.

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

# The state storage account's network firewall also has to actually let a
# GitHub-hosted runner in. A single-IP allowlist (however it was bootstrapped)
# blocks every hosted runner, and GitHub's published Actions IP ranges
# (7,280 CIDRs as of writing) exceed Azure's 200-rule-per-account IP-rule
# cap, so IP allowlisting is not an option. This was resolved by opening the
# network layer while keeping shared-key access disabled, so Azure AD auth
# remains the only way in:
az storage account update --name <your-tfstate-account> \
  --resource-group rg-novabank-ai-tfstate --default-action Allow

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
correct behaviour rather than a bug to work around. The AKS Cluster User
Role grant in step 3 above is likewise deferred until the cluster exists —
granting a role on a resource that doesn't exist isn't possible, so that
one command still needs to be run once AKS is created.

## What's actually done vs. still a placeholder

Everything above through step 5 has been run for real: app registration
`582a296a-5181-481a-a300-bda756372293`, all five federated credentials
(immutable-ID format), `AcrPush` + `Storage Blob Data Contributor` +
`Contributor` (on `rg-novabank-ai-dev`) role assignments, all GitHub
secrets/variables, and all four protected Environments (`azure-apply` and
`production` require review from the repository owner). `terraform-plan.yaml`
has run live and succeeded. Only the AKS-scoped role assignment (needs a
cluster that doesn't exist yet) and any real `terraform-apply`/`deploy` run
remain outstanding — both correctly gated behind protected-Environment
approval and, for `deploy.yaml`, behind AKS quota being resolved.

One side effect worth knowing about: `BUDGET_CONTACT_EMAIL` was set to the
email address active in the session that ran this setup, which differs from
the email the cost-alert resources were originally created with. The live
plan run correctly shows this as a 2-resource in-place update (cost budget
and action-group notification emails) — harmless, since a plan never
applies, but worth reconciling to whichever email should actually receive
budget alerts before any real `terraform-apply`.
