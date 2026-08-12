# ADR-014: public network access for ACR, AI Search and Azure OpenAI

Status: accepted

## Context

The Terraform modules for ACR (`main.tf`), Azure AI Search and Azure OpenAI
(`modules/ai/main.tf`) were originally designed private-only:
`public_network_access_enabled = false`, each with a dedicated private
endpoint and private DNS zone. That is the more secure default, and was the
correct starting point.

It did not survive contact with actually operating the CD pipeline (ADR-013)
and live-verifying the Azure adapters (Task 2 of the close-out plan,
`docs/portfolio/live-verification.md`). GitHub-hosted runners and this
project's own development machine have no route into the private VNet — a
private endpoint is only reachable from inside it. Every one of these three
resources was hit in turn:

- **AI Search and Azure OpenAI**: blocked live adapter verification outright
  (`403`/network-unreachable) until public access was enabled.
- **ACR**: blocked `container-publish.yaml`'s push job outright, and Azure
  additionally refused to enable public access while `export_policy` stayed
  disabled — the two are coupled, since a disabled export policy exists
  specifically to prevent images leaving over the network public access
  would open.

Each was fixed live, directly against the running resources, at the point it
blocked real work (`az resource update` / `az acr update`), **before** this
ADR or the corresponding Terraform changes existed. That left the state
storage account precedent from ADR-013 unrepeated here: code and reality had
drifted. This ADR closes that gap and is the record of the decision the
manual fixes were made under.

## Decision

Set `public_network_access_enabled = true` (and, for ACR, `export_policy_
enabled = true` — Azure requires them together) in the Terraform modules,
matching what was already true in the live subscription. In every case, the
resource's local/key-based authentication stays explicitly disabled:

| Resource | Local auth setting | Value |
| --- | --- | --- |
| ACR | `admin_enabled` | `false` |
| AI Search | `local_authentication_enabled` | `false` |
| Azure OpenAI | `local_auth_enabled` | `false` |

Azure AD / RBAC — role assignments scoped to specific principals
(`AcrPush`, `Cognitive Services OpenAI User`, `Search Index Data
Reader`/`Contributor`) — is therefore the only way into any of the three,
regardless of which network a request originates from. This is the same
trade-off already made once for the Terraform state storage account
(ADR-013): network-layer restriction traded for identity-layer restriction,
not for no restriction.

Private endpoints, private DNS zones and their VNet links are left in
place unchanged. Traffic that originates inside the VNet still resolves and
routes privately; this decision only removes the requirement that *all*
traffic must.

## Consequences

- `terraform-apply.yaml` no longer fights the manual fixes: a real apply
  reconciles state to the same posture already live, rather than reverting
  it. (This gap — code and reality silently diverging after a manual `az`
  fix — is exactly the kind of drift IaC exists to prevent; it should not
  recur.)
- `tests/test_repository_security.py::test_azure_modules_use_private_
  identity_and_cost_controls` updated to assert the new values and to
  explicitly assert the local-auth settings remain `false`, so a future
  change that opens the network *and* silently re-enables key-based auth
  would fail the test.
- Reduced defense-in-depth compared to the original private-only design:
  network-layer restriction is real, and removing it is a real trade,
  documented here rather than treated as a non-event because it happened
  via `az` first and Terraform second.

## Alternatives considered

- **Keep everything private, run CI from a self-hosted runner inside the
  VNet.** Architecturally correct, and what a production deployment of this
  platform should probably do — out of scope to stand up for a portfolio
  project's CI, and does not help local development from outside the VNet
  either.
- **IP-allowlist GitHub's published ranges instead of opening public
  access broadly.** Already tried and rejected for the state storage account
  in ADR-013: GitHub publishes thousands of CIDR ranges for Actions,
  exceeding Azure's per-resource IP-rule caps on every service checked so
  far.
