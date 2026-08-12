# Resource lifetime and cost tiers

Extends `docs/cost.md`'s Terraform-managed lifetime classes with the
resources created outside Terraform for live demonstration purposes.

| Tier | Resources | Lifetime rule |
| --- | --- | --- |
| Always on (Terraform) | Terraform-state storage account | Retain; low cost, preserves deployment state. |
| Active development only (Terraform) | Azure OpenAI, Azure AI Search, ACR, Key Vault | Created with explicit approval; standing charges while they exist. |
| **Demo-only (manual, not Terraform)** | **Azure Container Apps environment + app (`nova-aca-env`, `nova-gateway`)** | **Created via `make aca-up`, destroyed via `make aca-down` between demo sessions. Not part of the Terraform-managed platform — deliberately so: it exists specifically to answer "give me a live URL" while AKS remains quota-blocked, and should not accumulate as a second, parallel production surface.** |
| Configuration only until explicitly approved (Terraform) | AKS, managed Redis, workload identity | Terraform-ready; not applied. |

## Container Apps cost profile

Consumption plan, `min-replicas 0` (scales to zero when idle):

- **Idle**: effectively £0 — no vCPU/memory usage billed while there are zero replicas.
- **Active**: ~£0.076/hour of actual request-serving time at 0.5 vCPU / 1 GiB
  (Standard vCPU/Memory Active Usage, UK South retail pricing), plus
  negligible per-request cost (£0.40 per million requests). A full session
  of manual testing is pennies.
- Azure Container Apps' monthly free grant (180,000 vCPU-seconds, 360,000
  GiB-seconds, 2,000,000 requests) covers ordinary demo/test usage in full
  for a single environment like this one.
- The environment's Log Analytics ingestion reuses the existing
  `log-novabank-ai-dev` workspace (already covered in `docs/cost.md`), not a
  second workspace.

## Why not a per-service LoadBalancer or Container Apps as the permanent path

Container Apps is explicitly the interim, quota-driven path — see
`docs/portfolio/limitations.md` for the exact framing. The eventual AKS
ingress path (a single nginx ingress controller in front of everything,
not yet built as of this writing) costs one Azure Load Balancer at roughly
£15/month regardless of how many services sit behind it.
Exposing each service individually with `type: LoadBalancer` would instead
provision one Azure Load Balancer *per service* — multiplying that £15/month
by service count, for bare IPs with no TLS. That pattern is deliberately not
used anywhere in this platform.
