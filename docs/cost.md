# Azure demo environment cost and teardown

This environment is a short-lived portfolio sandbox, not an always-on service. The
estimate below uses Microsoft public retail prices in GBP for UK South, retrieved
11 August 2026, pay-as-you-go with 730 hours per month. It excludes discounts, tax
and variable consumption. Actual subscription billing is authoritative.

| Terraform component | Assumption | Estimated GBP/month |
|---|---:|---:|
| AKS system node | 1 × Linux `Standard_D2s_v5`, £0.0841/hour; AKS Free control plane | £61.39 |
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

The fixed standing estimate is approximately **£228–£231 per month**, before
telemetry ingestion, network data processing, model tokens, tax or support. A full
24-hour demo session is approximately **£7.50–£10**, depending mainly on telemetry
and inference. The Terraform default budget of £50 is an alert threshold, not a
guarantee or spending cap.

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
