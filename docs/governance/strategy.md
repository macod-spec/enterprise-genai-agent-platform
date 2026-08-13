# Platform strategy

## The product is the road, not the agent

Imagine forty teams inside a bank all decide to build AI agents at the same
time. Each one needs the same things: a way to authenticate callers, a way
to keep one team's customer data out of another team's retrieval results, a
way to stop one team's runaway prompt loop from spending another team's
model budget, an audit trail a regulator will accept, and a human-approval
step before anything irreversible happens. Built forty times, that is forty
authentication systems, forty retrieval filters, forty budget ledgers, forty
audit trails — most of them subtly wrong in a different way, because access
control and governance are exactly the kind of code that looks done long
before it is.

Built once, as a platform every team's agent runs on top of, it is one
thing to secure, observe, and improve — and every team that lands on it
inherits the current state of that work for free, including whatever gets
fixed after the fact.

That is the actual product here. NovaBank is the fictional test case;
`payment-disputes`, `complaints-triage`, `kyc-review`, and `fraud-alerts`
are four of its forty teams, standing in for the population the platform is
built to serve. Nothing about the platform's governance, retrieval scoping,
or budget enforcement is written in terms of any one of them by name — see
`docs/adrs/015-multi-tenancy-isolation.md` for what that means concretely
and how it is enforced in CI, not just claimed.

## Why this is a commercial argument, not just an engineering one

A platform that enforces isolation, cost attribution, and auditability once
turns three things that are normally cost centres into something closer to
infrastructure economics:

- **Marginal cost of the next team is small.** Onboarding is a config file
  (`config/tenants/<name>.yaml`), not a project. The fourth tenant added
  during this work was a single YAML file, zero application-code changes,
  verified working end-to-end before being counted as done.
- **Cost is attributable, not pooled.** Every tenant has its own token
  budget, and every spend-relevant metric carries a tenant label
  (`observability/grafana/dashboards/tenants.json`). A team that wants to
  run a more expensive model tier pays for it visibly; a team that doesn't
  isn't subsidising the one that does.
- **Governance evidence is produced once and reused.** The audit trail,
  approval workflow, and evaluation gates a regulator or an internal risk
  function wants to see exist at the platform layer. A new team's agent
  inherits them by being on the platform, not by re-proving them.

## Three horizons

**Now — proven locally, one real gap named plainly.** Isolation *between*
tenants is proven — given each caller's tenant claim is honest (state,
retrieval, quota, metrics; see the evidence matrix and
`docs/adrs/015-multi-tenancy-isolation.md`). It is not yet *enforced*
against a dishonest one: `X-Local-Tenant` is a client-supplied header with
nothing checking it against the caller's real identity, so every isolation
mechanism above sits on top of an unverified claim today. This is not in
the same category as the other current gaps — an AKS apply is a cost
decision awaiting sign-off, this is a security gap awaiting an afternoon of
work — and it is the immediate next item, ahead of everything else,
specifically because closing it converts the platform's central claim from
designed to enforced.

**Next — real identity, then real usage.** Two separate steps, in order.
First: resolve tenant from a verified Entra JWT claim instead of the local
header — the RS256 JWT validation infrastructure already exists in this
codebase for remote MCP auth (`mcp_boundary/remote_auth.py`), so this is
extension, not a build-from-nothing. Second, once that's closed: move one
real, low-stakes internal use case onto the platform under the existing
isolation model, with AKS as the deployment target instead of the
Container Apps demo path. That second step is the one that turns "the
isolation model is proven" into "a real team is trusting it" — but it
should not happen before the first.

**Later — self-service onboarding at the rate the config-file model
implies.** If onboarding truly stays a config change, the constraint on
team count stops being engineering effort and becomes review capacity —
which tenant bundle changes need what level of governance sign-off before
merge. That review policy, not more platform code, is the actual work of
this horizon.

## What "governance" means operationally here

Not a document review board. Concretely: every tenant bundle declares its
own `risk_tier` and `cost_centre`; the leakage test suite
(`tests/test_tenancy_leakage.py`) is the executable version of "prove
isolation holds," run in CI on every change, not audited after the fact;
and the zero-code-drift check (`scripts/check-tenant-drift.sh`) makes "no
platform code references a tenant by name" a build failure, not a code
review convention someone can forget.
