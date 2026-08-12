# ADR-013: GitHub Actions delivery pipeline — publish, plan, apply, deploy

Status: accepted

## Context

`ci.yaml` already builds, tests and scans on every push/PR, including a
container build and a zero-resource Terraform plan — but by design it never
logs into Azure, pushes an image, produces a non-zero Terraform plan, applies
anything, or deploys anywhere (its own trailing comment says so explicitly).
That gap — registry push, real plan review, apply, deployment — is what
remained of the delivery pipeline (master execution priority items 13–15).

## Decision

Four new, separate workflows, each `workflow_dispatch`-only (never triggered
by an ordinary push or PR) and each authenticating to Azure via OIDC
federation (`azure/login@v2`, no stored client secret):

- **`container-publish.yaml`** — builds, generates a CycloneDX SBOM, gates on
  HIGH/CRITICAL vulnerabilities (mirroring `ci.yaml`'s existing
  `container-build-only` job), then — behind a protected `container-registry`
  Environment — pushes to ACR and signs the pushed digest with **keyless**
  cosign (OIDC identity, public Rekor transparency log), distinct from the
  ephemeral-local-key blob signing `make sign-image` uses for offline `kind`
  validation: a registry-resident image gets a real, publicly verifiable
  signature, not a throwaway one. The SBOM is attached as a signed
  attestation on the same digest.
- **`terraform-plan.yaml`** — logs in, plans against real remote state with
  `enable_deployment=true`, uploads the plan as a reviewable artifact. This
  can never apply; it complements, not replaces, `ci.yaml`'s always-on
  offline zero-resource plan.
- **`terraform-apply.yaml`** — split into two jobs so approval is against
  what was actually reviewed: `plan` (no environment gate, produces and
  uploads a plan file) then `apply` (behind a protected `azure-apply`
  Environment) applies *that exact plan file* rather than re-planning and
  applying in one step, which could otherwise apply something a reviewer
  never saw.
- **`deploy.yaml`** — Helm-deploys a caller-supplied image digest (rejected
  outright if it is not a `sha256:` digest — no floating-tag deployment) to
  AKS behind a protected `production` Environment, then verifies the
  rollout with a real health-check smoke test and rolls back automatically
  on failure.

Every workflow that can change something (`container-publish`'s push job,
`terraform-apply`'s apply job, `deploy`) carries two independent safeguards:
a typed `workflow_dispatch` confirmation input *and* a protected Environment
requiring manual review. `terraform-plan`'s read-only plan and
`terraform-apply`'s plan job use lighter gating since they cannot change
anything by themselves.

None of this could run without a one-time Azure AD app registration,
federated credentials (one per branch/Environment trust boundary used), role
assignments, and GitHub secrets/variables — documented with exact commands
in `docs/ci-cd-azure-setup.md`. That setup was deliberately deferred at
first (creating an identity that lets automated CI act on a real Azure
subscription is a credentials/cloud-permissions decision for the platform
owner, not an implicit side effect of authoring workflow YAML), then run
with explicit approval on 2026-08-12. `terraform-plan.yaml` has since run
live end-to-end: OIDC login, a real `terraform init` against remote state,
and a real connected plan (5 to add, 2 to change, 0 to destroy — AKS,
managed Redis, workload identity federation, ACR-pull role assignment).
Two real bugs surfaced only by running it live rather than reasoning about
it: GitHub's OIDC subject claim uses an undocumented "immutable ID" format
(`repo:<owner>@<id>/<repo>@<id>:...`), and the Terraform state storage
account's single-IP firewall unconditionally blocks GitHub-hosted runners
(their published IP ranges — 7,280 CIDRs — exceed Azure's 200-rule
per-account cap, so allowlisting isn't possible; resolved by opening the
network layer while keeping shared-key access disabled, so Azure AD auth
stays the only way in). Full detail in `docs/ci-cd-azure-setup.md`.

## Consequences

- The delivery pipeline is complete as *code* (`actionlint` reports zero
  issues across all seven workflows) and `terraform-plan.yaml` is now a
  *proven, live capability*: a real OIDC-authenticated run against real
  remote state. `container-publish.yaml` and `terraform-apply.yaml` are
  identity- and RBAC-ready but have not actually been dispatched (a
  container push and a real infrastructure apply are each a further,
  separate decision). `deploy.yaml` cannot be proven live until AKS exists.
- `deploy.yaml` will fail cleanly at `az aks get-credentials` until AKS
  exists. That is no longer a hard quota block (`docs/azure-diagnosis.md`
  found and routed around the actual cause) — AKS just hasn't been created,
  since a real apply is a genuine ongoing cost held for explicit sign-off.
  This is the correct behaviour either way — this workflow is not meant to
  silently no-op or be disabled while AKS is unavailable, per the standing
  instruction to keep
  building everything that does not itself require a live cluster.
- Reusing `scripts/terraform-connected-plan.sh` as-is for the CI workflow
  was considered and rejected: that script depends on a gitignored local
  prerequisite file (`azure-prerequisites.json`) generated by a bootstrap
  script that assumes an interactive human (`az ad signed-in-user show`,
  `az ad group create`), which does not fit a service-principal CI identity.
  The workflow instead takes the same non-secret configuration
  (state-storage account, admin group id, budget contact) as GitHub Actions
  repository variables, set once after the human bootstrap step already run
  locally.

## Alternatives considered

- Trigger `container-publish` and `terraform-plan` automatically on push to
  `main`: rejected for now. A registry push and a live-credentialed Azure
  plan are both real, attributable actions against shared infrastructure;
  making them `workflow_dispatch`-only keeps every such action a deliberate,
  logged choice while the platform is still in active portfolio development.
  Revisit once the team and cadence justify it.
- Re-plan and apply in a single `terraform-apply` job: rejected — an
  approver would be approving a job, not the specific plan it is about to
  execute, which could differ from what they last saw if state changed
  between review and click.
