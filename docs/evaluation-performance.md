# Evaluation and performance gates

## Offline AI evaluation

The deterministic golden dataset contains synthetic cases across four release
dimensions: routing, grounding, safety and security. Every case checks the selected
route and agent, approval decision, expected source citation and expected bounded
error code. Both the aggregate score and every category must remain at 100%.

This strict threshold is appropriate for the deterministic local model. A later
non-deterministic model needs a reviewed statistical threshold, repeated runs,
versioned production-representative data and independent model-risk approval.
No real customer prompts or outputs belong in this repository.

Run the gate with `make evaluate`. Its aggregate, prompt-free result is written to
`.security-reports/evaluation.json`.

## Local performance baseline

`config/performance-baseline.json` defines a deliberately conservative, machine-
portable regression threshold for the in-process MCP gateway. The runner warms the
code path, takes three samples, gates on median throughput, and confirms injected
timeouts fail closed within a maximum duration. Results are written to
`.security-reports/load-failure.json`.

This measures local regression, not production capacity. It excludes network,
remote identity, database, model-provider and Kubernetes latency. Production SLOs
require environment-specific load, soak and concurrency testing with sanitised data.

Run the gate with `make reliability`.

## Operator demonstration

The local demo proves an operator can observe these controls without credentials
or cloud infrastructure:

1. A caller without `agent.invoke` is denied.
2. An authorised read-only investigation returns cited synthetic evidence.
3. A consequential financial instruction is not executed and creates a pending
   human-approval record.
4. Approval state stores only a query digest, while the MCP audit records only a
   tool-argument digest and bounded metadata.

Run it with `make operator-demo`. Sanitised evidence is written to
`.security-reports/operator-demo.json`; no raw prompt is included in that report.
