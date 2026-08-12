# Validate-only Azure architecture

The Terraform root is deliberately cost-locked. With its defaults every resource
and Azure data lookup uses `count = 0`; validation creates nothing. The repository's
`make terraform-zero-plan` gate may run a disabled plan without Azure credentials.
Never run `apply` during local development.

The target architecture includes locally validated modules for private AKS,
PostgreSQL, Redis, AI Search, Azure OpenAI, monitoring, budgets and private DNS/
endpoints for those services plus ACR and Key Vault. They remain behind the same
zero-resource deployment lock. See `docs/azure-private-module-design.md`.

Permitted local commands:

```bash
terraform fmt -check -recursive
terraform init -backend=false
terraform validate
make terraform-zero-plan
```

Resource creation requires both `enable_deployment=true` and the explicit
cost-acknowledgement value. CI never supplies either value and contains no apply
job.

See `docs/azure-sandbox-cost-review.md` for cost drivers, limitations and mandatory
controls before any future non-zero plan.

The manual, subscription-pinned `scripts/terraform-connected-plan.sh` uses the
secured remote backend, requires all providers to be registered, accepts only a
create-only plan, retains only a sanitised summary and contains no apply command.
See `docs/azure-connected-plan-review.md`.
