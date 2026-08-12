# Azure demo environment cost and teardown

This environment is a short-lived portfolio sandbox, not an always-on service. The
estimate below uses Microsoft public retail prices in GBP for UK South, retrieved
12 August 2026 (AKS system node row; see `docs/azure-diagnosis.md` for why the SKU
changed from the 11 August estimate), pay-as-you-go with 730 hours per month. It
excludes discounts, tax and variable consumption. Actual subscription billing is
authoritative.

| Terraform component | Assumption | Estimated GBP/month |
|---|---:|---:|
| AKS system node | 1 × Linux `Standard_D2ns_v6`, £0.1318/hour; AKS Free control plane; size is configurable but must remain a non-B-series AKS system-pool SKU with quota this subscription can actually use (`Standard_D2s_v5` cannot, `docs/azure-diagnosis.md`) | £96.21 |
| Azure AI Search | Basic, 1 search unit, £0.0765/hour | £55.85 |
| Container Registry | Premium registry unit, £1.2626/day | £38.40 |
| Managed Redis | `Balanced_B1`, one non-HA node, £0.0280/hour | £20.44 |
| PostgreSQL Flexible Server | Burstable `B1ms`, £0.0144/hour | £10.51 |
| PostgreSQL storage | 32 GiB at £0.1008/GiB-month | £3.23 |
| Private endpoints | 6 endpoints; estimate £0.008/hour each | £35.04 |
| AKS OS disk | 64 GiB managed disk allowance | £3–£6 |
| Log Analytics and Application Insights | Up to 1 GB/day caps; usage dependent | £0–£90+ |
| Key Vault | Standard operations; usage dependent | usually under £1 |
| Azure OpenAI | No provisioned throughput; token consumption only | workload dependent |
| DNS zones, identities, role assignments, VNet | No material standing charge | £0 |

The fixed standing estimate is approximately **£263–£266 per month**, before
telemetry ingestion, network data processing, model tokens, tax or support. A full
24-hour demo session is approximately **£8–£11**, depending mainly on telemetry
and inference. The Terraform default budget of £50 is an alert threshold, not a
guarantee or spending cap.

## Resource lifetime classes

The target architecture describes a complete platform; it does not imply that every
resource should run continuously during portfolio development.

| Lifetime | Resources | Operating rule |
|---|---|---|
| Always on | Terraform-state storage account and its resource group | Retain because it is low cost and preserves reviewed deployment state. Review monthly. |
| Active development only | Azure OpenAI account/deployments, Basic AI Search and PostgreSQL | Create only while developing or demonstrating the real model and RAG path. OpenAI is consumption based; Search and PostgreSQL accrue standing charges. Destroy after an inactive work period. |
| Demo week only | ACR, Managed Redis, AKS, private endpoints/DNS links, Log Analytics and Application Insights | Re-create from Terraform for the managed-platform demonstration, collect evidence, then destroy immediately. Local Compose and `kind` are the normal development runtime. |
| Configuration only until explicitly approved | AKS and workload identity federation | Keep Terraform, Helm, policy tests and `kind` evidence ready. The live preflight now passes (`docs/azure-diagnosis.md`); creation still awaits an explicit cost sign-off, not a quota clearance. Do not make AKS a dependency of Phase 2 application work. |

The connected apply path runs `scripts/azure-aks-preflight.sh` before Terraform
can apply. That preflight refuses the target if Azure still reports Free Trial
quota, an active spending limit, no regional compute quota entries, an unavailable
VM SKU, or a B-series AKS system node pool. This keeps the Pay-As-You-Go sandbox
from starting a partial deployment that cannot create AKS cleanly — it currently
passes with `Standard_D2ns_v6`.

The platform resource group is deliberately disposable. Data required after its
destruction must be exported to an approved non-production evidence location; the
demo environment is not a system of record.

Sources: the [Azure Retail Prices API](https://prices.azure.com/api/retail/prices),
[PostgreSQL pricing](https://azure.microsoft.com/en-gb/pricing/details/postgresql/flexible-server/),
[Managed Redis pricing](https://azure.microsoft.com/en-us/pricing/details/managed-redis/),
and [AI Search pricing](https://azure.microsoft.com/en-us/pricing/details/search/).

## Demo lifetime policy

- Create the environment only for a planned demo or target-environment test.
- Set the non-secret GitHub repository variable `AZURE_ENV_CREATED_AT` to the UTC
  apply start time, for example `2026-08-11T19:00:00Z`.
- The hourly `environment-age.yaml` workflow opens one deduplicated warning issue
  when the environment exceeds 24 hours.
- Destroy the whole `rg-novabank-ai-dev` platform resource group immediately after
  the demo. The separate Terraform state backend `rg-novabank-ai-tfstate` remains
  for state history and future deployments; review its small storage cost monthly.
- Azure Key Vault remains recoverable under its 90-day soft-delete and purge
  protection policy even though the active platform resource group is removed.

## Teardown procedure

First verify the signed-in Azure subscription and inspect the destruction plan:

```bash
az account show --query '{subscription:id,tenant:tenantId,user:user.name}'
DESTROY_DRY_RUN=1 make destroy
```

The dry run must report at least one deletion and zero creations. It does not alter
Azure. After reviewing that output, execute the exact resource-group confirmation:

```bash
DESTROY_CONFIRMATION=DELETE_rg-novabank-ai-dev make destroy
```

The script refuses a different subscription or tenant, missing remote-state
coordinates, a plan containing creates, or an incorrect confirmation token. It
applies the saved destroy plan and then verifies the platform resource group no
longer exists. Destruction is never scheduled or automatic.
