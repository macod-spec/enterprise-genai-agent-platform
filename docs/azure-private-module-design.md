# Private Azure module design

The Terraform design now separates target Azure capabilities into reviewable local
modules. All module calls use `count = local.deploy`, so the default disabled plan
instantiates none of them and continues to require no Azure credentials.

## Modules

| Module | Target services | Security defaults |
| --- | --- | --- |
| `compute` | User-assigned identity and AKS | Private control plane, local accounts disabled, Entra/Azure RBAC, workload identity, OIDC and a minimal system pool |
| `data` | PostgreSQL Flexible Server and Azure Cache for Redis | Public access disabled, Entra-only PostgreSQL authentication, TLS-only Redis, private endpoints and linked private DNS |
| `ai` | Azure AI Search and Azure OpenAI account | Public and local-key authentication disabled, managed identities, restricted outbound access, private endpoints and linked private DNS |
| `governance` | Application Insights, action group and resource-group budget | Workspace-based monitoring, local authentication disabled, internet query/ingestion disabled, and 50/80/100 percent cost notifications |
| `private-endpoints` | ACR and Key Vault private access | Reusable DNS zone, VNet link and endpoint construction; no public service path |

## Deployment inputs that deliberately fail closed

An enabled configuration must supply both the cost-acknowledgement token and at
least one Entra AKS administrator group and budget-alert recipient. The variables
contain no tenant identifiers, email addresses, credentials or subscription data by
default.

## Known design decisions before a connected plan

- AKS currently proposes a small fixed system pool and the free control-plane tier;
  node sizing and egress architecture require a capacity/network review.
- Service availability, regional SKU support and globally unique names can only be
  confirmed in the selected Azure subscription.
- RBAC assignments, federated workload credentials, remote state and diagnostic
  settings need subscription-specific identities and destinations.
- Model deployments are intentionally absent: model choice, capacity and quota need
  a separately approved evaluation and cost decision.
- The Redis resource models the current adapter target. Product lifecycle and the
  preferred managed Redis offering must be reviewed immediately before deployment.

No non-zero plan should be run until these decisions, the pricing-calculator
estimate and the controls in `docs/azure-sandbox-cost-review.md` are approved.
