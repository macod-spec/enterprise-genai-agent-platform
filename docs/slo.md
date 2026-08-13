# Platform service-level objectives

| SLI | Objective | Window |
|---|---:|---:|
| Gateway successful responses | 99.9% | 30 days |
| Workflow completion | 98% | 30 days |
| Gateway latency p95 | < 5 seconds | 7 days |
| MCP tool success | 99.95% | 30 days |
| Routing evaluation accuracy | >= 95% | every change |
| Critical hallucination/safety failures | 0 | every change |

For the 99.9% availability objective, multi-window alerts detect a fast 14.4x
burn over 5 minutes and 1 hour, and a persistent 6x burn over 30 minutes and 6
hours. Security and evaluation failures are release gates rather than
availability-budget events.
Synthetic local measurements demonstrate the model; production objectives require
real traffic review and business-owner approval.

## Local measurement implementation

Prometheus scrapes the gateway's `/metrics` endpoint every 15 seconds. Metric
labels are deliberately restricted to approved routes, agents, tools, outcomes,
methods, and status codes; customer queries and identity/request identifiers are
never labels. The provisioned Grafana dashboard displays request volume and
latency, workflow outcomes, MCP reliability, approval backlog, RAG effectiveness,
and model token estimates.

Local alert rules cover elevated HTTP 5xx rates, workflow latency, MCP failures
and timeouts, and approval backlog. These rules demonstrate the operating model;
named people, paging destinations and final thresholds must be agreed before a
production deployment. Accountable role ownership is recorded in
`docs/ownership.md`.
