# Limitations and production entry gates

This project demonstrates production-oriented design and local verification. It is
not represented as a live production banking system.

## Current limitations

- All records and policies are fictional; the default model, embeddings and
  Content Safety provider are free, deterministic mocks. Keyless Azure OpenAI,
  Azure AI Search and Azure Content Safety adapters exist behind the same
  interfaces but are unverified against a live Azure endpoint.
- Local identity headers are accepted only in `local` and `test` environments.
- PostgreSQL, Redis and authenticated remote MCP are locally exercised adapters.
- PII detection uses the small `en_core_web_sm` spaCy model, a real accuracy
  trade-off against the larger default model Presidio ships with.
- Groundedness evaluation is a deterministic term-overlap/citation scorer, not an
  LLM-judge; the CI gate proves the scorer's own correctness on known cases rather
  than grading the mock pipeline's (honestly ungrounded) output.
- The performance baseline measures an in-process boundary, not end-to-end capacity.
- SLO, RPO and RTO values are proposals until measured in the target environment.
- Terraform models a cost-locked Azure sandbox but has not been applied.
- Local `kind`/Helm validation signs images with an offline, ephemeral key. A
  separate keyless, OIDC-identity cosign signing path to a public Rekor log
  exists in `container-publish.yaml`. Azure OIDC federation is now live
  (`docs/ci-cd-azure-setup.md`) and `terraform-plan.yaml` has run successfully
  end-to-end against real remote state; `container-publish.yaml` and
  `terraform-apply.yaml` are identity-ready but have not actually been
  dispatched yet.
- AKS deployment remains blocked on Azure compute quota — confirmed still
  blocked in every region checked, not just uksouth. Filing an increase
  request requires the Azure Portal directly; the Support Tickets API refuses
  quota-only requests on a Free support plan. `deploy.yaml` would fail cleanly
  at `az aks get-credentials` until quota clears.
- The Terraform state storage account's network firewall was opened
  (`defaultAction: Allow`) to let GitHub-hosted runners reach it, since their
  published IP ranges (7,280 CIDRs) exceed Azure's 200-rule IP-allowlist cap.
  `allowSharedKeyAccess` remains `false`, so Azure AD auth is still the only
  way in, but this is a real reduction in network-layer defense in depth
  compared to a single-IP allowlist — an explicit, approved trade-off, not an
  oversight.

## Mandatory production gates

1. Approved DPIA, data classification, retention and model-risk assessment.
2. Entra workforce/workload identity, managed secrets and least-privilege RBAC.
3. Private network paths, egress controls and managed service security baselines.
4. Representative evaluation, abuse/red-team testing and external penetration test.
5. Capacity, soak, failover and recovery testing against agreed SLO/RPO/RTO values.
6. Signed provenance, controlled registry admission and canary/rollback verification.
7. Named service ownership, on-call coverage and exercised incident processes.

Cloud provisioning remains a separately approved activity because it changes cost,
risk and operational responsibility.
