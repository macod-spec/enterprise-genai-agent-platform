# Azure quota increase — portal request (prepared, not filed)

## Status check first: you probably don't need this for AKS anymore

`docs/azure-diagnosis.md` found that AKS was blocked by an unregistered
resource provider (fixed) and a per-subscription restriction on
`Standard_D2s_v5` specifically (routed around by switching the system node
pool default to `Standard_D2ns_v6`, which already has 10 vCPUs of quota and
no restriction). The AKS preflight check now passes against live Azure with
no quota increase filed. Read that document before filing anything below.

## One correction to the original request plan

The original plan asked for a **Standard BS Family vCPUs** increase. Do not
file that one for AKS: `scripts/azure-aks-preflight.sh` and
`infrastructure/terraform/variables.tf` both explicitly **refuse B-series
SKUs for the AKS system node pool** —

```
variable "aks_system_node_vm_size" {
  description = "AKS system node pool VM size. B-series is not allowed for system pools."
```

B-series is burstable (CPU credits that deplete under sustained load), which
is a real reliability risk for a system pool that must always have capacity
for core Kubernetes components (CoreDNS, metrics-server, CNI). Requesting
that family would grant quota the platform's own code refuses to use for
this purpose. If cheap burstable capacity is wanted later for a *user*
(non-system) node pool, that's a legitimate, separate ask — see the
alternative template below.

## If you still want headroom beyond what's already available

Current `standardDnv6Family` quota in uksouth is 10 vCPUs, 0 in use — enough
for several `Standard_D2ns_v6` system nodes without requesting anything. File
this only if you plan to scale beyond that (e.g., a multi-node system pool
plus separate user node pools).

**Portal click path:** Azure Portal → Subscriptions → (select
`Azure subscription 1`, `5677d45c-bce1-4375-ba74-7443b6a2a74c`) → **Usage +
quotas** → filter Provider = `Compute`, Location = `UK South` → search
`Dnsv6` → select `standardDnv6Family` → **Request quota increase** → enter
new limit → submit.

| Field | Value |
| --- | --- |
| Subscription | `5677d45c-bce1-4375-ba74-7443b6a2a74c` (Azure subscription 1) |
| Region | UK South |
| Provider | Compute |
| Quota name | Standard Dnsv6 Family vCPUs (`standardDnv6Family`) |
| Current limit | 10 |
| Suggested new limit | 20 (headroom for a multi-node system pool plus a small user pool) |

## Alternative: burstable capacity for a *user* node pool only

If cost matters more than headroom and a non-system pool is wanted on
B-series later, the actually-available, unrestricted burstable family in
uksouth (per the same live check) would need its own quota request —
re-run the candidate search in `docs/azure-diagnosis.md` against the
`B`-prefixed families before requesting, since availability/restriction is
per-family and per-subscription and may have changed by the time this is
read.
