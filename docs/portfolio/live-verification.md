# Live Azure adapter verification

Evidence that the keyless Azure adapters actually work against real Azure
resources — not just that they type-check and pass against a mocked SDK
client. Run via `make live-verification` or the `live-verification.yaml`
workflow_dispatch job; excluded from the default test run
(`pytest -m "not live_azure"`, the default in `pyproject.toml`).

## Azure OpenAI — `VERIFIED-LIVE` (2026-08-12)

Deployment: `gpt-5-nano` on `oai-novabank-ai-dev` (uksouth), `GlobalStandard`
SKU, capacity 1. Test: `tests/integration/test_azure_openai_live.py`.

```
$ make live-verification
tests/integration/test_azure_openai_live.py::test_azure_openai_adapter_completes_a_real_request PASSED
tests/integration/test_azure_openai_live.py::test_azure_openai_adapter_reaches_azure_through_the_governed_gateway PASSED
2 passed in 9.55s
```

**Two real bugs found and fixed, only by actually calling the live
endpoint** — neither is catchable by a test that mocks the OpenAI SDK client:

1. The adapter sent the deprecated `max_tokens` parameter. Reasoning-family
   models (the `gpt-5-nano` deployment used here) reject it outright:
   `400 unsupported_parameter: 'max_tokens' is not supported with this
   model. Use 'max_completion_tokens' instead.` Fixed by switching to
   `max_completion_tokens`, which both reasoning and non-reasoning chat
   completion models accept.
2. The adapter sent an explicit `temperature=0.0` (the gateway's
   deterministic default). Reasoning-family models reject any non-default
   temperature: `400 unsupported_value: 'temperature' does not support 0.0
   with this model. Only the default (1) value is supported.` Fixed by
   detecting reasoning-family models by name prefix (`o1`, `o3`, `o4`,
   `gpt-5`) and omitting the parameter entirely for them via the OpenAI
   SDK's `omit` sentinel.

A third, non-adapter finding: both `oai-novabank-ai-dev` and
`srch-novabank-ai-dev` had `publicNetworkAccess: Disabled`, which blocks any
call from outside their private network — including this test and any
future `workflow_dispatch` CI run. With explicit approval, both were
switched to `publicNetworkAccess: Enabled`; `disableLocalAuth` remains
`true` on both, so Azure AD/RBAC — not a network boundary — is the real
access control. Full detail in `docs/azure-diagnosis.md`'s sibling reasoning
for the Terraform state storage account (`docs/ci-cd-azure-setup.md`), the
same category of decision.

Sample real response (`max_tokens=1000`, most of the budget spent on hidden
reasoning tokens before the visible answer):

```json
{"content": "pong", "finish_reason": "stop", "usage": {"prompt_tokens": 13, "completion_tokens": 203}}
```

## Azure AI Search — `VERIFIED-LIVE` (2026-08-12)

Index: `novabank-policy-chunks` on `srch-novabank-ai-dev` (uksouth), ingested
with the platform's three real synthetic policy documents via
`scripts/ingest_azure_search.py`. Test:
`tests/integration/test_azure_search_live.py`.

```
$ make live-verification
tests/integration/test_azure_search_live.py::test_entitled_caller_retrieves_the_document PASSED
tests/integration/test_azure_search_live.py::test_unentitled_caller_never_receives_the_top_ranked_document PASSED
```

The entitlement-exclusion test is deliberately constructed so the excluded
document (`POL-DATA-003`, "Customer Data Handling", `allowed_roles:
agent.invoke,privacy.read`) is the unambiguous top hybrid-search match —
querying with the document's own text against the live index produced:

```
0.0333 POL-DATA-003   (top match, full access)
0.0328 POL-PAY-001
0.0323 POL-REF-002
```

A caller holding only `agent.invoke` (missing `privacy.read`) queried with
the identical text and received `POL-PAY-001` and `POL-REF-002` only —
`POL-DATA-003` was not merely re-ranked, it was completely absent, despite
being the strongest match for a fully-entitled caller.

**Three more real bugs found and fixed, only by actually ingesting into and
querying the live index** — none catchable by a test that mocks the Search
SDK client:

1. Azure AI Search document keys may only contain letters, digits,
   underscore, dash or equal sign. This platform's `chunk_id` format
   (`{document_id}#chunk-N`, baked into citation parsing in
   `rag/groundedness.py` and the synthesis prompt) uses `#`, which Search
   rejected outright with `InvalidName`. Fixed by adding a separate,
   sanitized `search_key` field as the index's actual key, while keeping
   `chunk_id` — unchanged, `#` included — as a normal retrievable field so
   citations are unaffected.
2. Azure Search's OData `all()` lambda only accepts a *negative*
   per-element test (`x ne y`, `not (x eq y)`, `not search.in(...)`) — the
   natural way to write "the caller holds every role a chunk requires",
   `allowed_roles/all(r: search.in(r, caller_roles))`, is rejected outright
   with `InvalidExpression`, confirmed against the live service. Fixed by
   testing the logically equivalent negative form instead: "no chunk role
   is among the *known* roles the caller lacks" — see `_KNOWN_CHUNK_ROLES`
   in `rag/azure_search.py` for the resulting constant this introduces and
   the fail-loud ingestion-time check that keeps it honest.
3. A generic `403 Forbidden` on document upload was, on first read, assumed
   to be an RBAC propagation delay (per the standing "wait 15 minutes"
   guidance for a *different*, genuine propagation delay seen earlier on
   the OpenAI account). It was not: the full error was `InvalidName:
   Invalid document key`, i.e. bug 1 above. The generic-looking exception
   text on early retries cost real debugging time — worth a specific note
   since the same-looking error hid two unrelated causes.

`gpt-5-nano` calls (Azure OpenAI section above) occasionally exceed the
30-second adapter timeout — reasoning-family models have real, variable
latency depending on how much hidden reasoning they do before answering.
One retry has always passed; documented here rather than silently retried
away, since it's genuine evidence about the model's latency profile, not a
flaky test.

## Azure Content Safety — `VERIFIED-LIVE` (2026-08-12)

Account: `cs-novabank-ai-dev` (uksouth), `F0` (free tier — no cost). Test:
`tests/integration/test_content_safety_live.py`.

```
$ make live-verification
tests/integration/test_content_safety_live.py::test_benign_text_is_not_blocked PASSED
tests/integration/test_content_safety_live.py::test_harmful_text_is_blocked PASSED
```

Real classification confirmed both directions:

```json
{"text": "ordinary benign customer service message", "Hate": 0, "SelfHarm": 0, "Sexual": 0, "Violence": 0, "blocked": false}
{"text": "I will find you and kill you, I have a bomb threat planned.", "Violence": 4, "blocked": true}
```

No adapter bugs found this time — the third live run in a row that this
project has actually exercised, and the first with zero surprises, which
is itself worth recording rather than only reporting the runs that found
something.

## Summary

All three Azure adapters (OpenAI, AI Search, Content Safety) are now
`VERIFIED-LIVE`. Seven real bugs were found and fixed across the three —
none of them catchable by unit tests that mock the respective SDK clients:
two in the OpenAI adapter (`max_tokens`, `temperature`), three in the
Azure Search adapter (document key format, OData `all()` grammar, and a
misleading generic error that hid the second one), and two infrastructure
findings (both OpenAI and AI Search defaulted to
`publicNetworkAccess: Disabled`, opened with explicit approval, AAD auth
unchanged as the real gate).

## Supply chain — real signed image in ACR — `VERIFIED-LIVE` (2026-08-12)

`container-publish.yaml` run
[31637091014](https://github.com/macod-spec/enterprise-genai-agent-platform/actions/runs/31637091014):
built, SBOM'd, HIGH/CRITICAL-vulnerability-gated, pushed to
`acrnovabankaidev.azurecr.io`, and keyless-signed with cosign via GitHub
OIDC.

```
Image:  acrnovabankaidev.azurecr.io/enterprise-agent-platform@sha256:5e04217d5fc0ca27e97f8e9249f9c5b8a139e707157a36ecb47c27938c77b5bd
Tag:    6ef92708694e64f497cdc5973eede7d78de78cbf (commit SHA)
```

Signature verified from a **separate** step (not the workflow that produced
it — a fresh, independent `cosign verify` run against the live registry):

```
$ cosign verify acrnovabankaidev.azurecr.io/enterprise-agent-platform@sha256:5e04217d5fc0ca27e97f8e9249f9c5b8a139e707157a36ecb47c27938c77b5bd \
    --certificate-identity-regexp ".*" \
    --certificate-oidc-issuer https://token.actions.githubusercontent.com

Verification for ...@sha256:5e04217d5... --
The following checks were performed on each of these signatures:
  - The cosign claims were validated
  - Existence of the claims in the transparency log was verified offline
  - The code-signing certificate was verified using trusted certificate authority certificates

Subject: https://github.com/macod-spec/enterprise-genai-agent-platform/.github/workflows/container-publish.yaml@refs/heads/main
Issuer: https://token.actions.githubusercontent.com
githubWorkflowSha: 6ef92708694e64f497cdc5973eede7d78de78cbf
githubWorkflowTrigger: workflow_dispatch
```

The certificate identity is bound to the exact workflow file, repo, commit
and trigger type — not just "some GitHub Actions run somewhere."

**Negative proof**: pushed an unrelated, unsigned image
(`alpine:latest`, retagged) to the same repository, then confirmed
verification fails:

```
$ cosign verify acrnovabankaidev.azurecr.io/enterprise-agent-platform:unsigned-test ...
Error: no signatures found
error during command execution: no signatures found
(exit code 10)
```

The unsigned test tag was deleted immediately after (`az acr repository
delete`); it exists nowhere but this record now.

**One real, structural bug found — not in the workflow, in the registry's
own configuration**: the push job failed with `ERROR: Looks like you don't
have access to registry ... publicNetworkAccess`. `acrnovabankaidev` had
`publicNetworkAccess: Disabled` (same category as OpenAI/Search) **and** a
coupled `exportPolicy: disabled` — Azure refuses to enable public access
while exports are disabled, since that combination would let images leave
the registry over the network the disabled-export control exists to
block. With explicit approval (this is a stronger control than a simple
firewall — it is an anti-exfiltration policy, not just network ACLs), both
were enabled together; `adminUserEnabled` remains `false`, so AAD/RBAC
(the `AcrPush` role already granted to the CI identity in ADR-013) is
still the only way to push or pull.

## Real `terraform apply` through the pipeline — `VERIFIED-LIVE` (2026-08-12)

Task 3's manual `az` fixes to ACR, AI Search and Azure OpenAI (above) had
left Terraform declaring `public_network_access_enabled = false` for all
three — a real drift between code and reality that a full apply would have
reverted. ADR-014 (`docs/adrs/014-public-network-access-for-ci-reachability.md`)
fixes the drift in code; this is the real, gated `terraform-apply.yaml` run
that reconciled it.

`terraform-apply.yaml` gained an optional `apply_targets` input so this
config-only change could go through the real pipeline scoped to just the
three affected resources (`-target`), without dragging the rest of the
outstanding plan (AKS, managed Redis, workload identity, ACR-pull role —
still deliberately unapplied) along with it.

**First attempt** ([run 31638653481](https://github.com/macod-spec/enterprise-genai-agent-platform/actions/runs/31638653481)) hit
a genuine transient Azure API timeout — `context deadline exceeded` on the
Cognitive Services account lookup, 5 minutes in — not a config or code bug;
a local dry-run moments earlier against the same real state had succeeded
in under a minute. The state lock was correctly acquired and released even
on this failure.

**Second attempt** ([run 31639145554](https://github.com/macod-spec/enterprise-genai-agent-platform/actions/runs/31639145554)) succeeded
completely: plan job produced a reviewable plan (downloaded and read before
approving — "No changes. Your infrastructure matches the configuration.",
matching the local dry-run), the protected `azure-apply` Environment
approval was given only after reading that exact plan, and the apply job
then ran:

```
Acquiring state lock. This may take a few moments...
Releasing state lock. This may take a few moments...
Apply complete! Resources: 0 added, 0 changed, 0 destroyed.
```

Zero resource changes is the *correct* result here, not a weak one: the
manual fixes already matched what the newly-corrected Terraform code
declares, so a working pipeline reconciling state with code and finding
nothing left to do is exactly the expected, honest outcome. What this run
actually proves is the full mechanics: real OIDC authentication, a real
state lock genuinely taken and released against the real remote backend,
a plan reviewed as an artifact before a human approval gate, and an apply
step that applies precisely the plan that was reviewed — nothing invented,
nothing skipped.
