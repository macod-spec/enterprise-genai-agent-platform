# Azure identity and network review

## Identity contract

- GitHub Actions must authenticate through OIDC federation to a dedicated plan
  identity; client secrets and storage-account keys are prohibited.
- A separate protected-environment identity performs an approved apply. The plan
  identity has read plus narrowly scoped validation permissions and cannot apply.
- AKS uses workload identity and OIDC. Each workload receives its own user-assigned
  identity and federated credential, service account and minimum data-plane role.
- Human administration uses Entra groups, privileged access workflow and audited
  elevation. Individual users are not embedded in Terraform RBAC assignments.
- State access uses Azure AD authentication and OIDC as shown in
  `infrastructure/terraform/backend.hcl.example`.

Required connected-plan inputs are subscription ID, tenant ID, approved Entra AKS
administrator group object IDs, state-backend coordinates and budget recipients.
None is committed to the repository.

## Network contract

- AKS exposes a private API server and uses a dedicated subnet.
- Data, AI, ACR and Key Vault public access is disabled and each service uses a
  dedicated private-endpoint subnet with linked private DNS.
- Network policy denies lateral and outbound traffic by default. Approved DNS,
  identity, monitoring and explicitly registered MCP destinations are exceptions.
- A connected design review must select an egress firewall/NAT path, DNS resolver,
  on-premises connectivity and CI runner path to the private control plane.
- Diagnostic and flow logs must use approved private ingestion paths and retention.

## Review decisions still requiring the target organisation

1. Subscription/management-group placement, policies and permitted regions/SKUs.
2. Hub/spoke address allocation, routing, firewall and private DNS ownership.
3. Identity owners, access-review cadence and emergency access process.
4. GitHub-hosted versus private runners capable of reaching private endpoints.
5. Data residency, encryption-key ownership and log-retention requirements.

This document is a design review, not evidence that those controls are active in an
Azure tenant.
