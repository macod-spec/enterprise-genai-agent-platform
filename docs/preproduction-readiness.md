# Pre-production readiness gates

The platform can enter a provider-connected non-zero planning stage only when every
item below has an accountable owner and dated approval.

| Gate | Required evidence | Current status |
| --- | --- | --- |
| Cost | Dated calculator/export including all services, traffic, logs and tax assumptions | Public-retail research only; subscription quote required |
| Identity | OIDC federation, separate plan/apply identities and Entra groups | AKS admin group and workload identities partly deployed; GitHub OIDC absent |
| Network | Approved CIDRs, private DNS, egress and runner connectivity | Design complete; organisation decisions absent |
| State | Private storage backend, Azure AD auth, locking, recovery and access review | Backend deployed with Azure AD auth and default-deny networking; CI access absent |
| Security | Threat review, IaC/SAST/SCA/container gates and external penetration scope | Local gates complete; external test absent |
| Privacy/model risk | DPIA, data classification, retention and model approval | Templates complete; formal approvals absent |
| Reliability | Target-environment load, failover, DR and alert routing | Local evidence complete; target exercise absent |
| Operations | Named owner/on-call, runbook exercise, change and rollback approval | Local documents complete; organisation assignment absent |

## Connected plan rules

The first non-zero plan is review-only. It must use remote state, OIDC, synthetic
data, an isolated sandbox subscription, approved variables and `-out`. The plan JSON
must be scanned, costed and reviewed; it must not be applied. Plan artifacts are
treated as sensitive and retained only in an access-controlled workflow.

## Deployment rules

An apply is a later, separately approved action. It requires a protected environment,
four-eyes approval, signed artifacts, change record, maintenance window, verified
rollback, budget alerts and an automatic expiry/teardown owner.
