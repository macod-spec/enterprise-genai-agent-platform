# Limitations and production entry gates

This project demonstrates production-oriented design and local verification. It is
not represented as a live production banking system.

## Current limitations

- All records and policies are fictional; the default model, embeddings and
  Content Safety provider are free, deterministic mocks so local development
  and CI incur no cost. Keyless Azure OpenAI, Azure AI Search and Azure
  Content Safety adapters exist behind the same interfaces and are now
  live-verified (`docs/portfolio/live-verification.md`) — seven real bugs
  were found and fixed only by running them against real Azure endpoints,
  none catchable by a test that mocks the respective SDK client.
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
  exists in `container-publish.yaml` and has now run for real: a real image
  is signed in ACR and independently verified
  (`docs/portfolio/live-verification.md`). `terraform-plan.yaml` and a
  scoped `terraform-apply.yaml` run have also completed successfully against
  real remote state. `deploy.yaml` (AKS deploy) remains undispatched — it
  needs a live AKS cluster, which does not exist yet.
- AKS was believed blocked on Azure compute quota; diagnosis
  (`docs/azure-diagnosis.md`) found the real cause was an unregistered
  `Microsoft.Compute` resource provider stacked with a per-subscription
  `NotAvailableForSubscription` restriction on the originally-configured VM
  size, `Standard_D2s_v5` — not a hard zero-quota state. Fixed by registering
  the provider and switching the AKS system node pool default to
  `Standard_D2ns_v6` (confirmed unrestricted, quota already available); the
  live preflight check now passes. AKS still has not actually been created —
  a real `terraform apply` is a genuine ongoing cost (~$127/month for one
  node at pay-as-you-go pricing) and remains a separate, explicit decision,
  not a technical blocker anymore.
- The Terraform state storage account's network firewall was opened
  (`defaultAction: Allow`) to let GitHub-hosted runners reach it, since their
  published IP ranges (7,280 CIDRs) exceed Azure's 200-rule IP-allowlist cap.
  `allowSharedKeyAccess` remains `false`, so Azure AD auth is still the only
  way in, but this is a real reduction in network-layer defense in depth
  compared to a single-IP allowlist — an explicit, approved trade-off, not an
  oversight.
- The live demo endpoint (`nova-gateway`, Azure Container Apps) runs the real
  signed image against the real Azure OpenAI/AI Search/Content Safety
  adapters. It is not, however, a stand-in for AKS-based production
  deployment: it uses `APP_ENV=local`, meaning authentication is the
  platform's local-identity-header mechanism, not a verified production
  identity provider. There is deliberately no IP allowlist — a rotating
  home IP is unsuitable as an access control and documenting it anywhere
  would itself be a leak surface — so the real controls are the gateway's
  own auth (every agent endpoint returns 401 without valid `X-Local-*`
  headers; no anonymous access) and a low per-tenant token budget that caps
  blast radius even for an authenticated caller. It is also demo-only by
  design (`docs/cost-tiers.md`, `make aca-up`/`make aca-down`), separate
  from the Terraform-managed platform, and is expected to be torn down
  between sessions rather than left running. The Kubernetes ingress path
  this would eventually be replaced by (a single nginx controller,
  cert-manager TLS, host-based routing) has not been built yet.
- **Tenant identity is not yet enforced, only isolated once claimed.**
  `X-Local-Tenant` is a client-supplied header, not a verified claim: any
  caller that can reach the endpoint can set it to `payment-disputes`,
  `complaints-triage`, `kyc-review`, or `fraud-alerts` and receive that
  tenant's correctly-scoped results, whether or not they have any actual
  relationship to that tenant. Every isolation control this platform builds
  — RLS, retrieval entitlement filtering, per-tenant budget, tenant-labelled
  metrics — sits underneath that header and is only as trustworthy as it
  is. `tests/test_tenancy_leakage.py` proves tenant A cannot see tenant B's
  data *given each caller's tenant claim is honest*; it does not, and
  cannot, prove a caller can't lie about which tenant it is, because
  nothing currently checks. This is the same local-identity-header
  limitation as caller identity generally (see above), but it is called out
  separately here because it is the direct precondition for every
  multi-tenancy claim in `docs/adrs/015-multi-tenancy-isolation.md` and the
  evidence matrix — tenant isolation should be read as **designed and
  locally proven under a trusted-claim assumption**, not as **enforced
  end-to-end**, until tenant resolution comes from a verified Entra JWT
  claim instead of this header.

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
