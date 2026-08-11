# Azure connected plan review

## Scope and result

The confirmed sandbox subscription was first used for a provider-connected,
non-zero Terraform plan on 2026-08-11. Remote Azure Storage state and Azure CLI
identity were used and provider auto-registration was disabled. After review and
explicit approval, a later 41-create plan was applied.

The apply is currently partial. The secured state backend, Entra AKS administrator
group, `rg-novabank-ai-dev`, networking, ACR, Key Vault, PostgreSQL, Azure OpenAI,
AI Search, monitoring, managed identities, RBAC and private endpoints exist. AKS,
Managed Redis, workload federation and their dependent resources remain incomplete.
Existing resources may incur charges until destroyed.

## Security findings resolved during plan review

The first successful connected plan exposed provider defaults not apparent in
static validation. The configuration was hardened to disable:

- Log Analytics local authentication and public query/ingestion;
- Redis access keys, with Entra authentication explicitly enabled;
- ACR export policy and trusted-service network bypass; and
- default outbound subnet access.

Telemetry daily ingestion caps were reduced to 1 GB. The final Terraform validation,
connected plan, secret scan, Bandit scan and HIGH/CRITICAL Trivy configuration scan
all passed.

## State backend posture

The backend requires HTTPS and TLS 1.2, disables shared-key access and public blob
access, uses Azure AD data-plane authorization, and applies a default-deny network
rule with the approved operator IP as an exception. That exception must be reviewed
or replaced by a private runner/private endpoint before production use.

## Decision

The initial apply was explicitly approved but did not complete. Resumption is paused
until repository publication, shutdown tooling, cost documentation and environment
age warnings are in place. Formal production network, privacy/model-risk and
external security approvals remain outstanding.
