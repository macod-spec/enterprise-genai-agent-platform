# Limitations and production entry gates

This project demonstrates production-oriented design and local verification. It is
not represented as a live production banking system.

## Current limitations

- All records and policies are fictional; the model and embeddings are deterministic.
- Local identity headers are accepted only in `local` and `test` environments.
- PostgreSQL, Redis and authenticated remote MCP are locally exercised adapters.
- The performance baseline measures an in-process boundary, not end-to-end capacity.
- SLO, RPO and RTO values are proposals until measured in the target environment.
- Terraform models a cost-locked Azure sandbox but has not been applied.
- The signing exercise is offline and ephemeral rather than identity-backed keyless
  production signing.

## Mandatory production gates

1. Approved DPIA, data classification, retention and model-risk assessment.
2. Entra workforce/workload identity, managed secrets and least-privilege RBAC.
3. Private network paths, egress controls and managed service security baselines.
4. Representative evaluation, abuse/red-team testing and external penetration test.
5. Capacity, soak, failover and recovery testing against agreed SLO/RPO/RTO values.
6. Signed provenance, controlled registry admission and canary/rollback verification.
7. Named service ownership, on-call coverage and exercised incident processes.

Cloud provisioning remains a separately approved activity because it changes cost,
risk and operational responsibility.
