# Disaster recovery plan

## Scope and objectives

Approval state and audit evidence are the critical recoverable data. The proposed
production targets are an RPO of 15 minutes and an RTO of 60 minutes. These are
design targets until business owners approve them and a managed PostgreSQL
point-in-time recovery exercise measures them in a non-production Azure tenant.

## Recovery sequence

1. Declare the incident and freeze mutating approval decisions.
2. Preserve logs, request identifiers, image digest and database recovery point.
3. Restore PostgreSQL to an isolated instance and validate schema and record counts.
4. Start the previously signed image digest against the isolated database.
5. Validate health, authorization, pending approvals and audit continuity.
6. Obtain incident-commander and service-owner approval before redirecting traffic.
7. Reconcile decisions made near the recovery point and record actual RPO/RTO.

Redis is rebuildable acceleration/state and must not be the only production system
of record. If Redis is selected for approval storage in a non-production exercise,
AOF persistence and restoration must be explicitly tested. Signing keys, access
tokens and database credentials are restored from the approved secrets system,
never from backups of application data.

## Local evidence

`make operational-readiness` creates an isolated SQLite approval record, copies a
backup, restores it to a new database, validates record integrity and confirms the
original query is absent. Temporary databases are deleted after the exercise; only
aggregate JSON evidence is retained. This proves the recovery workflow mechanics,
not the proposed production RPO/RTO.
