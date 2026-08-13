# Operations runbook

## Triage

1. Declare severity: SEV-1 for security compromise, unsafe financial action or
   broad outage; SEV-2 for sustained SLO burn or degraded critical workflow;
   SEV-3 for contained degradation.
2. Assign incident commander, operations lead, communications lead and scribe.
3. Confirm `/health/live` and `/health/ready`, then correlate `X-Request-ID`
   across JSON logs, MCP audit and traces.
4. Check error-budget alerts, authorization outcomes, MCP timeout/error rates,
   approval backlog and the current signed image digest.

## Containment and recovery

1. Preserve pending approvals and route unsafe or unavailable automation to an
   authorised human; never bypass the gate.
2. Revoke suspected tokens or credentials, rotate them, and inspect access and
   repository history. Do not print credentials during diagnosis.
3. Disable the affected MCP domain or model route before broadening permissions.
4. Roll back to the previous verified image digest. Do not mutate a running pod.
5. Follow `docs/disaster-recovery.md` for state restoration and reconciliation.
6. If policy results are wrong, quarantine the corpus version and verify
   provenance, role filters and offline evaluation before rebuilding the index.

## Closure

Record the timeline, user impact, detection gap, actual SLI/RPO/RTO, evidence
locations, corrective owners and deadlines. A SEV-1 or SEV-2 requires a blameless
review and verification of corrective actions before closure.
