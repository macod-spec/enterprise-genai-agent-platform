# ADR-007: Use Langfuse for LLM observability and evaluation

Status: accepted

## Context

Standard OpenTelemetry covers service health, but operators also need prompt and
trace inspection, token and cost analysis, datasets, experiments and evaluation
results. The platform must self-host this capability and keep sensitive payload
capture disabled or redacted by default.

## Decision

Use self-hosted Langfuse as the Phase 2 LLM operations layer, fed from the gateway
and agent through its OpenTelemetry-compatible tracing integration. Azure Monitor
remains the infrastructure and service telemetry backend. Langfuse is an optional
Compose profile locally and a demo-week-only workload in managed environments.

Prompt and response bodies are not collected by default. Trace metadata uses
pseudonymous tenant/request identifiers, and retention and access controls are
environment-specific.

## Consequences

- One UI connects traces, model usage, costs, datasets and evaluation evidence.
- OTel-based instrumentation reduces lock-in and keeps operational metrics in the
  existing Azure Monitor path.
- Self-hosting introduces PostgreSQL, upgrades, backup and access-control duties.
- The integration must degrade safely: an unavailable observability backend must
  not fail inference or weaken policy enforcement.

## Alternatives considered

- Arize Phoenix provides strong open-source, OTel-native tracing and evaluation.
  It remains the preferred fallback if its evaluation workflow better fits later
  requirements; Langfuse was selected for the combined trace, prompt, dataset and
  cost-management workflow needed by this portfolio.
- Provider-native monitoring alone was rejected because it cannot correlate the
  complete multi-provider agent path or hold provider-neutral evaluation evidence.

## Implementation status

Implemented: a `langfuse` Compose profile (`compose.yaml`) running self-hosted
Langfuse v4 (web, worker, its own Postgres, ClickHouse, MinIO, Redis), bootstrapped
via `LANGFUSE_INIT_*` env vars so a fixed local project/API-key pair exists without
a manual UI step. The shared `otel-collector` (`observability/otel/collector.yaml`)
fans out traces to both the existing `debug` exporter and a new `otlphttp/langfuse`
exporter, authenticated with `Authorization: Basic <base64(public:secret)>` and
`x-langfuse-ingestion-version: 4`, per Langfuse's OTLP/HTTP ingestion contract
(gRPC is not supported). The app itself is unchanged — it always exports OTLP to
the collector; Langfuse is purely a collector-side fan-out target, so an
unavailable/inactive Langfuse degrades safely with no effect on inference.

Locally validated end-to-end in this session: brought up the full profile, called
`POST /api/v1/model-gateway/generate`, and confirmed via the Langfuse public API
(`GET /api/public/v2/observations`) that the model gateway's GenAI span was
ingested and auto-classified as a `GENERATION` named `"chat mock-deterministic"` —
proving Langfuse's OTel GenAI semantic-convention auto-recognition
(`gen_ai.system`, `gen_ai.request.model`, `gen_ai.usage.*`) works against the spans
emitted by `model_gateway/telemetry.py` (ADR-006) with no Langfuse-specific
instrumentation required.

Two real defects were found and fixed during validation, both unrelated to
Langfuse itself:
- ClickHouse migrations failed with "no Zookeeper configuration" until
  `CLICKHOUSE_CLUSTER_ENABLED=false` was set explicitly on `langfuse-web` and
  `langfuse-worker` (the image's internal default did not resolve to single-node
  mode without it).
- `agent-gateway` crash-looped with `sqlite3.OperationalError: unable to open
  database file` because the Dockerfile never created `/var/lib/platform` before
  switching to the non-root user, so Docker seeded the named volume as
  root-owned. Fixed by creating and `chown`-ing the directory as root before
  `USER 10001:10001` (`Dockerfile`).

Known limitation: the `langfuse-web` Docker healthcheck (`wget ... 127.0.0.1:3000`)
fails inside the container even though the service answers correctly on the
published host port — a Docker Desktop loopback-networking quirk, not a service
fault. `docker compose ps` will show `unhealthy` for `langfuse-web` even when it
is working; this needs a different probe (e.g. a Node-based check) to be
cosmetically correct.

Not yet done: cost/usage-model mapping in Langfuse's UI (no model catalog entry
exists for `mock-deterministic`, so price fields are null there — expected, not a
bug), and no CI job runs this profile automatically. Langfuse remains
demo-week-only per the resource lifecycle policy — do not leave it running
unattended.
