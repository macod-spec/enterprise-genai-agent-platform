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

## Azure Content Safety — pending (Task 2c)

No Content Safety account exists yet. `F0` (free tier) is available in
uksouth; account creation and live verification are tracked separately.
