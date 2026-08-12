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

## Azure AI Search — pending (Task 2b)

`publicNetworkAccess` is now `Enabled` and a live, authenticated
`GET /indexes` call succeeds (`200`, empty index list — no index created
yet). Full live verification, including the entitlement-exclusion test,
is tracked separately.

## Azure Content Safety — pending (Task 2c)

No Content Safety account exists yet. `F0` (free tier) is available in
uksouth; account creation and live verification are tracked separately.
