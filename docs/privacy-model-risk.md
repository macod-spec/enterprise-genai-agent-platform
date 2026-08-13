# Privacy and model-risk gate

This repository uses fictional data only. A real-data deployment is prohibited
until the following evidence has an owner, approval and review date.

## Privacy assessment

- document lawful purpose, data controller/processor roles and data categories;
- minimise prompts, retrieved fields, audit content and retention periods;
- map regional storage, subprocessors and international transfers;
- implement data-subject access/deletion and legal-hold procedures;
- demonstrate encryption, access review, breach response and deletion evidence;
- complete a DPIA where required by the responsible privacy function.

## Model-risk assessment

- record model/provider/version, intended use and prohibited decisions;
- measure routing quality, groundedness, safety, bias and failure modes;
- define human oversight, override authority and contestability;
- test prompt injection, data leakage, tool misuse and provider outage;
- establish drift thresholds, revalidation cadence and rollback criteria;
- require independent approval for material model, tool or policy changes.

Engineering evidence exists for parts of this list: a deny-by-default model
allowlist and per-tenant budget (ADR-006), Presidio-backed PII detection (ADR-009),
an Azure Content Safety guard (ADR-010), and a deterministic groundedness scorer
for synthesized RAG answers with its own CI-integrated correctness gate (ADR-012).
This is engineering evidence only, produced against a deterministic mock model and
fictional data. It does not constitute privacy, legal, compliance or model-risk
approval, and does not substitute for bias testing, drift monitoring or
independent review against a live model.
