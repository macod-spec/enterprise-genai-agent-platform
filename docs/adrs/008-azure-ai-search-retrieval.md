# ADR-008: Use Azure AI Search as the primary retrieval engine

Status: accepted

## Context

The enterprise RAG path requires keyword and vector retrieval, semantic reranking,
metadata filters, document-level entitlement enforcement and managed operations.
PostgreSQL is already required for durable agent state, so pgvector would reduce
the number of services, while Azure AI Search provides a purpose-built search
control plane.

## Decision

Use Azure AI Search for the production-shaped hybrid retrieval path. Index entries
carry immutable source identifiers, classification and entitlement principals.
The application constructs server-side filters from authenticated claims; client
supplied filters are never trusted. Retrieval results retain citations and are
subject to groundedness checks before generation is returned.

Keep the retriever interface provider-neutral and retain a local in-memory fixture
for deterministic tests. PostgreSQL remains the durable application-state store,
not the primary enterprise search engine.

## Consequences

- The project demonstrates managed hybrid/vector search and security trimming.
- Search is an additional always-billable service while active and must follow the
  development-session/demo-week lifetime policy.
- Index schema, embedding versions and reindex/runbook procedures become governed
  platform artifacts.
- The abstraction preserves a migration path if cost, residency or scale changes.

## Alternatives considered

- PostgreSQL with pgvector would consolidate storage and work well for smaller
  corpora, but would require us to operate more ranking and search behavior and
  provides a weaker demonstration of the target Azure platform.
- Vector-only retrieval was rejected because enterprise content benefits from exact
  keyword matching and metadata filters as well as semantic similarity.
