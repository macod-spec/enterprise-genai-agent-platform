# ADR-009: PII detection and masking in the model gateway

Status: accepted

## Context

Requests and model responses can contain personal or financial data (names,
emails, phone numbers, card numbers, UK sort codes). Sending this to a third
-party model provider, or echoing it back unmasked, is a data-protection and
model-risk concern. Detection and enforcement need to live in one place with
executable tests, not be left to individual agents to remember.

## Decision

Use Microsoft Presidio's detection engine (`presidio-analyzer`) as the single
enforcement point for PII, integrated directly into `ModelGateway.generate()`
(ADR-006) rather than scattered across agents. Every request message is
scanned before it reaches a provider adapter, and every provider response is
scanned before it is returned, using the same policy in both directions.

`presidio-analyzer` runs against the small `en_core_web_sm` spaCy model
(not the default `en_core_web_lg`) to keep the dependency footprint and
container size reasonable; regex-based recognizers (email, phone, credit
card, IBAN, SSN) do not depend on the NLP model's accuracy. A custom
`PatternRecognizer` adds a `UK_SORT_CODE` entity type for the NovaBank
domain.

Policy is expressed as two disjoint entity sets:

- `mask_entities` — replaced in place with a `<ENTITY_TYPE>` placeholder
  (default: `PERSON`, `EMAIL_ADDRESS`, `PHONE_NUMBER`, `IP_ADDRESS`).
- `block_entities` — the whole request is rejected with `PiiBlockedError`
  before any provider call, or the whole response is discarded if the
  provider generated one (default: `CREDIT_CARD`, `IBAN_CODE`, `US_SSN`,
  `UK_SORT_CODE`).

Audit metadata (a Prometheus counter and, for blocks, the HTTP error detail)
carries only entity **type** and **action** (`masked` / `blocked`) — never
the matched text or its position. This mirrors the platform's existing rule
that spans and metrics never carry prompt/response content (ADR-007).

`presidio-anonymizer` (Presidio's own masking package) is deliberately **not**
a dependency: every recent release unconditionally pins
`cryptography<49.0.0`, which carried three known CVEs (PYSEC-2026-3552/3553/
3554) at the time of writing. `presidio-analyzer` alone has no `cryptography`
dependency. Masking here is a simple, ~15-line span substitution over
`presidio-analyzer`'s detection results, which is all `presidio-anonymizer`
would have added for the "replace" operator this platform uses.

## Consequences

- One enforcement point, matching ADR-006's principle that policy stays in
  the gateway, not the agents.
- PII scanning happens on every model-gateway call by default
  (`PII_PROTECTION_ENABLED=true`); it can be disabled per-environment but not
  per-agent, keeping the control fail-safe rather than opt-in.
- Blocking is symmetric: a disallowed entity in either the request or a
  provider's response fails the whole call. This is simpler to reason about
  than direction-specific policy, at the cost of occasionally discarding an
  otherwise-useful response that happened to contain, e.g., a hallucinated
  card number.
- The `en_core_web_sm` model trades NER accuracy (particularly `PERSON`
  recall on unusual names) for a ~12 MB dependency instead of Presidio's
  default ~560 MB `en_core_web_lg`. Regex-anchored entity types are
  unaffected.
- A future `cryptography`-clean `presidio-anonymizer` release, or a switch to
  its `Encrypt`/`Decrypt` operators for reversible tokenisation, would be a
  natural extension; today's masking is one-way and irreversible by design.
- `weasel` (a `spacy` dependency) transitively pulls in `tldextract`, which
  tries to cache the public suffix list under `$HOME` on first use. The
  non-root container user has no writable `$HOME`, so this logs a benign
  `Permission denied` warning and falls back to an uncached lookup; it does
  not affect detection and no request fails because of it. Left unfixed for
  now — tracked as a minor container-hygiene cleanup (set `HOME` to a
  writable path for the `app` user), not a functional defect.

## Implementation status

Implemented in `src/enterprise_genai_platform/safety/pii.py`
(`PresidioPiiDetector`, `PiiPolicy`, `PiiBlockedError`) and wired into
`ModelGateway.generate()` (`src/enterprise_genai_platform/model_gateway/gateway.py`).
On by default (`PII_PROTECTION_ENABLED=true`); the shared detector is built
once per process (`model_gateway/factory.py`, `@lru_cache`) since loading the
spaCy pipeline takes ~1s.

Verified: 14 unit/HTTP tests (`tests/test_pii.py`,
`tests/test_model_gateway.py`) covering masking, blocking, per-tenant
disable, and that raw PII text never appears in a metric label or HTTP error
body. `make check`/`audit`/`sast`/`secrets`/`licenses` all re-verified clean
after adding `presidio-analyzer`, `spacy` and the `en_core_web_sm` model as
dependencies. The container image was rebuilt and re-scanned (0 HIGH/CRITICAL
findings), and redeployed through the full local pipeline — `kind`/Helm with
Kubernetes security assertions, and a direct `docker run` smoke test that
sent a real PII-bearing request through `/api/v1/model-gateway/generate` and
confirmed the masked response — to confirm the new dependencies actually
work at runtime inside the hardened container, not just in the dev venv.

A real Dockerfile bug was found and fixed during this validation: the
runtime stage installed wheels via `pip install /wheels/*`, a bare glob that
cannot resolve a direct-URL dependency (the `en_core_web_sm` wheel) against
the local wheel cache and instead tried to re-fetch it over the network
inside a stage with no matching distributions available, failing the build.
Fixed by switching to `pip install --no-index --find-links=/wheels
enterprise-genai-agent-platform`, which resolves the whole dependency graph
against the local wheel directory correctly and offline.

## Alternatives considered

- `presidio-anonymizer` for masking: rejected on supply-chain grounds (see
  above); its behaviour is trivially reproduced without the vulnerable pin.
- `en_core_web_lg` (Presidio's documented default): rejected as
  disproportionate container/dependency weight for a demonstration platform;
  can be swapped in later without changing the `PresidioPiiDetector` API.
- Azure AI Language PII detection (`azure-ai-textanalytics`): would remove
  the local spaCy dependency but adds a network round-trip and cost to every
  gateway call, and a new connected-Azure dependency purely for text
  classification. Deferred; Presidio's offline detection is a better fit for
  cost-conscious local/CI operation and can be revisited if accuracy proves
  insufficient.
