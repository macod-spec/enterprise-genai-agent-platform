# ADR-012: Groundedness evaluation for synthesized RAG answers

Status: accepted

## Context

`PolicyAgent` (used by the routing workflow and its golden-case evaluation)
returns raw retrieved evidence chunks, not a synthesized natural-language
answer — there was nothing to evaluate for groundedness. Producing an answer
and evaluating whether it is actually supported by its cited evidence are two
distinct capabilities the platform did not yet have.

## Decision

Add both, as a new capability additive to the existing routing/evidence
flow rather than a change to it:

- `rag/synthesis.py`: `synthesize_grounded_answer` builds a prompt containing
  only the evidence `AuthorizedRetriever` already returned (never
  unauthorized content) plus an instruction to cite every claim with the
  evidence's bracketed chunk id, then calls the owned `ModelGateway`
  (ADR-006). Because it goes through the model gateway like any other call,
  the allowlist, budget, PII (ADR-009) and content-safety (ADR-010) controls
  all apply automatically — nothing here bypasses them. An empty evidence set
  short-circuits to a fixed refusal rather than asking a model to answer
  from nothing.
- `rag/groundedness.py`: `GroundednessEvaluator` is a deterministic,
  rule-based scorer, not an LLM judge — reproducible in CI without a live
  model, and every score is explainable. It reports:
  - **term overlap**: the fraction of the answer's significant terms (after
    stripping citation brackets, which are scored separately) that also
    appear somewhere in the retrieved evidence text.
  - **citations found**: chunk ids the answer cited, extracted from its own
    `[DOC-ID#chunk-N]` bracket format.
  - **fabricated citations**: cited chunk ids that do not exist in the
    evidence that was actually retrieved — a direct hallucinated-citation
    signal.
  - **is_grounded**: a composite requiring term overlap at or above a
    configurable threshold, at least one real citation, and zero fabricated
    ones.

Both are wired into a new `POST /api/v1/rag/answer` endpoint, deliberately
separate from `PolicyAgent`/`OperationsWorkflow` and their existing,
well-tested golden-case evaluation — this is additive, not a replacement,
and carries no risk of regressing the routing/tool-grounding evaluation that
already exists.

Groundedness is an **evaluation** signal, not a policy gate: the endpoint
always returns the answer along with its groundedness report, rather than
blocking a low-scoring one the way the PII or content-safety guards block
their own violations. A caller (or a future UI) decides what to do with a
poorly-grounded answer; the platform's job here is to make that visible, not
to suppress it.

## Consequences

- `POST /api/v1/rag/answer` is a real, testable demonstration of the full
  RAG chain: authorized retrieval → cited synthesis → groundedness
  evaluation, all through the owned model gateway.
- The mock model provider's response is a generic acknowledgement, not a
  real answer, so it is *honestly* ungrounded (no citation, low term
  overlap) when evaluated — confirmed against the real running container,
  not just asserted in a unit test. This is the expected and correct
  behaviour of the safety net, not a bug: grading the mock's output against
  a "must be grounded" bar would be meaningless, so the CI quality gate
  (`scripts/groundedness-evaluation.py`, `make groundedness-evaluation`)
  instead proves the *evaluator* correctly classifies four known cases
  (grounded-and-cited, unrelated, correct-but-uncited, fabricated-citation)
  and separately records the honest mock-pipeline sample as evidence, rather
  than asserting the mock must pass. That gate runs in CI
  (`.github/workflows/ci.yaml`) alongside the existing `evaluate` step.
- A real scoring bug was found and fixed while building the evaluator's own
  test cases: citation brackets like `[POL-PAY-001#chunk-1]` were being
  tokenized into the term-overlap calculation, so `pol`, `chunk` and similar
  fragments counted against every properly-cited answer. Citations are now
  stripped from the prose before term extraction; citation correctness is
  scored separately, as intended.
- Once Azure OpenAI is live-validated (ADR-006), the same endpoint and
  evaluator should produce meaningfully high groundedness scores without any
  code change — only the configured model changes.

## Alternatives considered

- An LLM-as-judge groundedness evaluator: rejected for now — it would need
  its own model-gateway call (cost, latency, and a second place PII/content-
  safety would need to apply), and is not reproducible offline in CI the way
  a rule-based scorer is. Worth revisiting once a live model is available,
  as a complement to (not replacement for) the deterministic scorer.
- Changing `PolicyAgent` itself to synthesize and return a grounded answer:
  rejected — it is the routing workflow's specialist, exercised by existing
  golden-case evaluation that checks tool-level evidence grounding, not
  answer-level groundedness. Conflating the two risked regressing a
  well-tested path for no benefit; the new endpoint delivers the same
  capability without touching it.
