# Azure compute diagnosis (2026-08-12)

This document records the actual root cause of the AKS "quota blocked" state
that had been carried in `docs/roadmap.md` since the subscription's Free
Trial→Pay-As-You-Go upgrade, and how it was resolved without any Azure
Support request.

## What was actually wrong (three findings, not one)

### 1. `spendingLimit` was already `Off` — not the cause

```json
{
  "quotaId": "PayAsYouGo_2014-09-01",
  "spendingLimit": "Off"
}
```

The subscription has been on Pay-As-You-Go with no spending limit since the
upgrade. This rules out the most common cause of "everything shows zero
quota" on a converted subscription.

### 2. `Microsoft.Compute` was `NotRegistered` — the real cause of "zero everywhere"

```
$ az provider show --namespace Microsoft.Compute --query registrationState -o tsv
NotRegistered
```

This is why `az vm list-usage` previously returned **zero usage/quota
entries in every region checked** (uksouth, ukwest, westeurope, northeurope,
eastus) — not because the subscription had no quota, but because the
resource provider that serves that data had never been activated for this
subscription. Registering it (`az provider register --namespace
Microsoft.Compute`, free, reversible, ~80 seconds to complete) immediately
surfaced the subscription's real quota state: **232 usage entries** in
uksouth alone, most VM families sitting at their standard default limit (10
vCPUs for general-purpose families, more for some).

### 3. `Standard_D2s_v5` specifically — the AKS module's configured VM size — is doubly blocked, and unrelated to (2)

```json
{
  "family": "standardDSv5Family",
  "quota_limit": 0,
  "restrictions": [
    {"reasonCode": "NotAvailableForSubscription", "type": "Location", "values": ["uksouth"]},
    {"reasonCode": "NotAvailableForSubscription", "type": "Zone", "values": ["uksouth"]}
  ]
}
```

Even with `Microsoft.Compute` registered, `Standard_D2s_v5` remains
unusable: its family (`standardDSv5Family`) has a **0 vCPU limit**, and
separately, Azure has marked the SKU itself `NotAvailableForSubscription` in
uksouth — a per-subscription eligibility restriction, not a quota number.
`Standard_D2s_v3` and `Standard_D2s_v4` were also checked and carry the same
`NotAvailableForSubscription` restriction, despite their families showing 10
vCPUs of quota. Whatever cohort this subscription was placed in restricts it
from the Dsv3/Dsv4/Dsv5 generations specifically in this region — quota and
SKU eligibility are two different gates, and D2s_v5 was blocked by both.

## The fix: a different, already-usable SKU — no Support request needed

Cross-referencing every VM size Azure reports as available in uksouth
against this subscription's actual per-family quota surfaced
`Standard_D2ns_v6`: 2 vCPUs, 8 GB RAM, premium storage support
(`PremiumIO: true`), Hyper-V Generation 2, available in all three uksouth
availability zones, **zero restrictions**, and its family
(`standardDnv6Family`) already has a 10 vCPU limit with 0 in use.

```
$ az vm list-skus --location uksouth --size Standard_D2ns_v6 --all -o json | jq '.[0].restrictions'
[]
```

Changed the default in three places (`infrastructure/terraform/variables.tf`,
`scripts/azure-aks-preflight.sh`, `scripts/terraform-connected-apply.sh`) from
`Standard_D2s_v5` to `Standard_D2ns_v6`. Re-ran
`scripts/azure-aks-preflight.sh` against the live subscription afterward:

```json
{
  "aks_system_node_vm_size": "Standard_D2ns_v6",
  "compute_usage_entries": 232,
  "matching_skus": 1,
  "restricted_skus": 0,
  "passed": true,
  "reason": "AKS subscription and SKU preflight passed."
}
```

**AKS is not currently blocked by a hard quota-zero state.** It was blocked
by an unregistered resource provider (now fixed, free) stacked with a
per-subscription SKU restriction on the originally-configured VM family (now
routed around by picking a different, unrestricted family). No code or
infrastructure was applied to reach this conclusion — this is a diagnosis
and a config default change only.

## What this does *not* do

- It does not create AKS. `terraform apply` has not been run. That is a real,
  billable action (`Standard_D2ns_v6` prices at $0.174/hour pay-as-you-go
  Linux in uksouth as of 2026-08-12 — roughly $127/month for one node
  running continuously) and is being held for explicit sign-off, consistent
  with the standing rule to report estimated monthly cost before anything
  billable runs.
- It does not mean every region or every VM family is unrestricted for this
  subscription — only that a specific, suitable alternative was found and
  confirmed for the AKS system node pool's actual requirements (uksouth,
  general-purpose, premium-storage-capable, non-B-series).
- `docs/azure-quota-request.md` is still written, for the case where a
  larger or specific family really is needed later — but filing it for AKS
  itself is very likely unnecessary now given the above.
