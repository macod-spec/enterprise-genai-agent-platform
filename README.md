# Enterprise GenAI Agent Platform

A local-first, production-oriented paved road for building, securing, evaluating,
and operating enterprise AI agents. Ordinary developer commands remain cloud-free,
while an explicitly approved Azure sandbox is currently partially deployed.

For a concise reviewer journey, architecture diagrams and a repeatable interview
walkthrough, start with the [portfolio evidence pack](docs/portfolio/README.md).

## Current milestone: local platform plus Azure sandbox deployment

The first project layer establishes checks that every later Python, agent, MCP,
RAG, infrastructure, and deployment change must pass.

### Local setup

Python 3.12 or 3.13 is recommended.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/pre-commit install
```

Run the fast developer checks:

```bash
make check
```

Run the fuller local security suite:

```bash
make security
```

Dependencies are resolved in the committed `uv.lock`, including source and wheel
SHA-256 hashes. Regenerate it only after intentional dependency review:

```bash
.venv/bin/uv lock
make lock-check
```

`make security` also enforces a dependency license allowlist and runs six
repository-owned Semgrep rules from `.semgrep.yml`. Semgrep runs in a pinned,
isolated container with the repository mounted read-only, preventing scanner
dependencies from changing the application environment.

With Docker Desktop running, build the runtime image, generate a local CycloneDX
SBOM, and fail on fixable high/critical container vulnerabilities:

```bash
make container-security
```

The container gate exports the image to the ignored `.security-reports` directory
and scans that archive with pinned Trivy. It does not expose the Docker socket to
the scanner, upload the image inventory, push the image, or deploy it.

Sign and verify that archive locally with an ephemeral Cosign key:

```bash
make sign-image
```

The signer is digest-pinned, runs with networking disabled, receives no Docker
socket, and destroys its encrypted private key after verification. Only the
public key and detached signature remain in `.security-reports`. This demonstrates
the artifact-verification contract; production should use workload-identity-based
keyless signing and a transparency log.

Run the complete ephemeral Kubernetes integration gate:

```bash
make kind-integration
```

This builds, scans and signs the image, creates a Docker-hosted `kind` cluster,
loads the image directly without a registry, deploys the Helm chart into a
restricted Pod Security Standards namespace, tests health/readiness/metrics and
security contexts, then deletes the cluster automatically.

These commands inspect local files only. They do not authenticate to Azure,
provision resources, publish images, push commits, or deploy anything. Separate
guarded scripts under `scripts/terraform-connected-*` operate the approved Azure
sandbox and must never be confused with the default local workflow.

### Azure sandbox status

The secured remote-state backend and part of `rg-novabank-ai-dev` were deployed on
2026-08-11 with explicit approval. Networking, ACR, Key Vault, PostgreSQL, Azure
OpenAI, AI Search, monitoring, identities and private endpoints exist and may incur
charges. AKS, Managed Redis and their dependent federation/RBAC resources remain
incomplete. See `docs/azure-connected-plan-review.md` and `docs/cost.md` for the
live status and shutdown policy.

The Azure Terraform default can also be proved safe with
`make terraform-zero-plan`. It performs a disabled, refresh-free plan and fails
unless the plan contains zero resource changes. See
[docs/azure-sandbox-cost-review.md](docs/azure-sandbox-cost-review.md).

## Security policy

- Secrets belong in an ignored `.env` file or an approved secret manager.
- `.env.example` contains names and safe local defaults only.
- High-confidence Bandit findings fail the security check.
- Known vulnerable Python dependencies fail `pip-audit`.
- Secret findings fail `detect-secrets` unless explicitly reviewed.
- Cloud provisioning requires a separate, explicit manual action.

See [docs/security.md](docs/security.md) for the control model and planned
end-to-end scanning layers.

## Local Agent Gateway

The first runtime component is a FastAPI gateway with secure defaults. Start it
after bootstrapping the development environment:

```bash
make run
```

Public health checks:

```bash
curl http://127.0.0.1:8000/health/live
curl http://127.0.0.1:8000/health/ready
```

Local-only authentication deliberately uses development headers so the platform
can be exercised without Entra ID or cloud resources:

```bash
curl \
  -H 'X-Local-User: developer' \
  -H 'X-Local-Roles: platform.viewer' \
  http://127.0.0.1:8000/api/v1/platform/info
```

These headers are rejected when `APP_ENV` is `development`, `staging`, or
`production`. A verified identity provider must be implemented before any such
environment can serve protected routes.

### Local LangGraph supervisor

The gateway includes a bounded supervisor workflow backed by a deterministic
mock model. It routes only to approved domains and sends unknown or consequential
financial actions to human review:

```bash
curl -X POST \
  -H 'Content-Type: application/json' \
  -H 'X-Local-User: developer' \
  -H 'X-Local-Roles: agent.invoke' \
  -d '{"query":"Why did this payment fail?"}' \
  http://127.0.0.1:8000/api/v1/workflows/route
```

The mock provider is deterministic, makes no network calls, uses no API key, and
incurs no model or cloud charges.

### Synthetic NovaBank investigation

The connected operations workflow can route to read-only customer, payments, and
policy specialists. All bundled records are fictional and explicitly classified
as synthetic:

```bash
curl -X POST \
  -H 'Content-Type: application/json' \
  -H 'X-Local-User: developer' \
  -H 'X-Local-Roles: agent.invoke' \
  -d '{"query":"Why is CUST-1098 payment transaction TXN-5001 delayed?"}' \
  http://127.0.0.1:8000/api/v1/workflows/investigate
```

The specialists cannot mutate accounts or execute payments. Customer contact
details are masked, transaction/customer relationships are checked, evidence is
source-labelled, and consequential actions are routed to human review.

### Governed MCP boundary

Specialists no longer access the synthetic repository directly. Four approved
tools are defined through the official MCP SDK:

- `customer.get_customer`
- `customer.get_accounts`
- `payments.get_transaction`
- `policy.search`

The in-process MCP gateway validates every input and output, propagates caller and
request identity, enforces per-agent allowlists and caller roles, limits calls,
applies timeouts and bounded retries, and writes metadata-only audit records. Raw
tool arguments are represented in audit records by a SHA-256 fingerprint.

The three SDK servers have local stdio entry points under `mcp/`. A separate
local-only Streamable HTTP entry point supports customer, payments, or policy
domains with stateless sessions and RS256 bearer-token verification. It validates
issuer, audience, expiry, issued-at time, subject, token ID, and a distinct
`mcp:<domain>` scope. Missing, tampered, expired, wrong-audience, and wrong-scope
tokens fail closed. The server binds to loopback and retains the SDK's DNS
rebinding protection.

The remote entry point is `mcp/remote-server/server.py`. It requires a public-key
file and explicit issuer; private signing keys are never loaded by the server.
This is a local reference implementation rather than a replacement for managed
Entra workload identity in a deployed environment.

### Secure local RAG

The Policy MCP tool retrieves from a bundled fictional policy corpus using a
deterministic local embedding and vector index. This implementation downloads no
model and calls no external service. It provides the interface that can later be
implemented by Azure AI Search.

The ingestion and retrieval controls include:

- strict Markdown metadata schemas and UTF-8 validation;
- document size and control-character limits;
- rejection of common indirect prompt-injection instructions and active markup;
- immutable document versions and SHA-256 provenance;
- deterministic overlapping chunks and stable chunk identifiers;
- role filters applied before vector ranking;
- bounded query and result sizes;
- citations containing document, version, chunk, and provenance identifiers;
- no LLM execution of retrieved document instructions.

The customer-data policy deliberately requires both `agent.invoke` and
`privacy.read`, demonstrating that a semantically relevant document is still
excluded when the caller lacks its metadata permissions.

## Additional platform layers

The repository also includes a validated Skill Registry and governance API,
backend-neutral human-approval records, a twelve-case offline quality/security gate,
optional OpenTelemetry export, a Python consumer SDK, a hardened multi-stage
Dockerfile, local Compose configuration, a secure Helm chart, cost-locked Azure
Terraform, non-deploying GitHub security workflows, an agent starter template and
a Backstage scaffolder definition.

The release gate scores routing, grounding, safety and adversarial security cases
independently. Reproducible local performance thresholds and a secure operator
walkthrough are also available:

```bash
make evaluate
make reliability
make operator-demo
```

See [docs/evaluation-performance.md](docs/evaluation-performance.md) for scope,
evidence and the limitations of the local baseline.

### Local observability stack

The gateway exposes bounded-cardinality Prometheus metrics at `/metrics` when
`METRICS_ENABLED=true`. Metrics cover HTTP requests and latency, workflow outcomes,
MCP calls and latency, RAG retrievals and hits, estimated model tokens and cost,
and pending approvals. Labels never contain queries, user identifiers, request
identifiers, tool arguments, or arbitrary route/error text.

Prometheus alert rules and a provisioned Grafana dashboard are included. To run
the full local stack, create the ignored environment file and set a unique local
Grafana password before starting Compose:

```bash
cp .env.example .env
# Edit .env and set GRAFANA_ADMIN_PASSWORD to a unique local value.
docker compose up --build
```

The local endpoints bind only to loopback:

- Gateway: `http://127.0.0.1:8000`
- Prometheus: `http://127.0.0.1:9090`
- Grafana: `http://127.0.0.1:3000`

The OpenTelemetry collector receives local traces and writes them to its debug
exporter. Compose does not authenticate to or create resources in any cloud.

### Durable state, locally

Approval persistence supports SQLite for local/test use plus authenticated
PostgreSQL and Redis adapters. Only a SHA-256 digest of the workflow query is
stored. Decisions use a conditional update or atomic compare-and-set so an
approval cannot be decided twice. Staging and production configuration fails
closed if SQLite is selected or a remote connection URL is missing.

Run the disposable integration gate with:

```bash
make durable-state-integration
```

The command creates random in-memory test passwords, starts PostgreSQL and Redis
on loopback-only ports, verifies reconnect persistence and atomic decisions, and
then removes the containers and their test volumes. It never contacts a cloud.

### Local load and failure testing

```bash
make reliability
```

This runs concurrent governed MCP calls, injects deterministic downstream
timeouts, verifies bounded retries and fail-closed results, and writes the
aggregate report to `.security-reports/load-failure.json`. The report contains no
queries, tokens, subjects, or other request-level data.

Terraform defaults to zero resources and requires two deliberate settings before
any resource can be considered. No CI workflow contains Azure login, Terraform
plan/apply, registry push, kubectl or deployment steps.
