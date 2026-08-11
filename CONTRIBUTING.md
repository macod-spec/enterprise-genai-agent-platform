# Contributing

Use Python 3.12 or 3.13, run `make bootstrap`, and keep all examples fictional.
Before requesting review run `make security`, `helm lint`, `terraform fmt -check`
and `docker compose config`. Never run cloud deployment commands as part of a
contribution. New tools require an allowlist decision, threat-model update,
contract tests, audit fields and a skill-registry change.
