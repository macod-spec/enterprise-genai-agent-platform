# Azure sandbox cost and deployment review

## Decision

Default local workflows remain limited to formatting, validation and a disabled
zero-resource plan. Separately, an explicitly approved provider-connected apply was
started on 2026-08-11 and is currently partial. Existing sandbox resources may incur
charges; further apply work is paused behind shutdown and cost-control gates.

## Default-plan cost conclusion

With `enable_deployment=false`, every Azure resource and the Azure client lookup use
`count = 0`. The executable plan gate verifies that the plan contains zero resource
changes. Therefore the default plan creates no Azure usage cost.

## Dated public-retail finding

On 2026-08-11, the unauthenticated Microsoft Azure Retail Prices API returned a UK
South Linux consumption rate of GBP 0.0841 per hour for `Standard_D2s_v5`. At 730
hours, the single proposed AKS system node is approximately GBP 61.393 per month
before disks, networking, monitoring or any other platform service. That lower bound
already exceeds the Terraform default budget of GBP 50, so a non-zero plan is
blocked—not merely awaiting execution.

The system node size is configurable through `aks_system_node_vm_size`, but the
guardrails deliberately refuse B-series sizes for the AKS system pool. They are
cheap, but not an acceptable system-pool target for this platform. Any lower-cost
substitution must be a supported non-B-series SKU and must pass the live Azure
SKU/quota preflight immediately before apply.

The sanitised query result and calculation are recorded in
`config/azure-retail-price-snapshot.json`. The API provides public retail prices
without subscription discounts; a complete calculator export remains mandatory.
See the official [Azure Retail Prices API documentation](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices).

## Update, 2026-08-12: default VM size changed

`docs/azure-diagnosis.md` found `Standard_D2s_v5` carries a 0-vCPU family
quota and a `NotAvailableForSubscription` restriction specific to this
subscription in uksouth — unrelated to the cost conclusion above, but it
meant the default in `aks_system_node_vm_size` had to change to a SKU this
subscription can actually use: `Standard_D2ns_v6` (2 vCPU, 8 GB, premium
storage, confirmed unrestricted). Re-querying the same unauthenticated Retail
Prices API on 2026-08-12 for `Standard_D2ns_v6` in uksouth returned GBP
0.1318/hour Linux consumption — at 730 hours, approximately **GBP 96.21 per
month** for the single proposed system node, before disks, networking or
monitoring. This is higher than the superseded `Standard_D2s_v5` estimate
above and still exceeds the Terraform default budget of GBP 50 — the
non-zero-plan block described above still applies, for a larger margin than
before.

## Proposed sandbox cost drivers

| Component | Cost/risk characteristic | Sandbox decision |
| --- | --- | --- |
| Resource group and virtual network | No or low direct usage cost; enables dependent services | Retain as foundation only |
| Premium ACR | Fixed tier cost; private networking capability | Do not create until image workflow is approved |
| Key Vault | Transaction-based; purge protection affects deletion lifecycle | Do not create until managed identity design is approved |
| Log Analytics | Ingestion and retention can grow unexpectedly | Retain 30-day proposal; add daily cap before deployment |
| AKS | Node pools, disks, load balancers and monitoring dominate cost | Private module is validate-only; local kind remains runtime evidence |
| PostgreSQL and Redis | Always-on compute/storage and backup costs | Use only for a time-boxed integration environment |
| AI Search and model endpoints | Provisioned capacity and token usage | Require explicit quotas and synthetic evaluation first |
| APIM and private endpoints | Tier and hourly/network charges | Defer until identity/network requirements are approved |

Prices are intentionally not hard-coded because Azure regional prices and offers
change. Immediately before any enablement, export a dated estimate from the official
Azure Pricing Calculator for the selected subscription, region, currency and usage
profile, then obtain owner approval.

## Required controls before a non-zero plan

1. A named owner, expiry date and deletion runbook for the sandbox.
2. A reviewed calculator estimate at or below the approved monthly ceiling.
3. Azure budget alerts at 50%, 80% and 100%, plus service quota limits.
4. Remote encrypted state, locking and restricted state access.
5. Entra workload identity; no stored client secret or local developer credential.
6. Private endpoints, deny-by-default egress and public access disabled.
7. Required tags for owner, environment, classification, cost centre and expiry.
8. CI separation: plan may be reviewed, but apply requires a protected environment
   and explicit human approval.
9. AKS preflight: the active subscription must no longer report Free Trial quota
   or an active spending limit, the target region must return compute quota entries,
   and the chosen system node SKU must be available and unrestricted.

The `monthly_budget_gbp` variable feeds a validate-only budget resource with 50%,
80% and 100% notifications. An enabled plan still requires reviewed alert recipients
and must prove that the budget is accepted by the target subscription.

## Evidence

Run `make terraform-zero-plan`. The sanitised aggregate result is written to
`.security-reports/terraform-zero-plan.json`; the binary plan and full plan JSON are
temporary and deleted after validation to avoid retaining potentially sensitive
provider data.
