# ADR-011: Azure AI Search hybrid retrieval with server-side entitlement filtering

Status: accepted

## Context

ADR-008 chose Azure AI Search as the production-shaped retrieval engine and
required that "the application constructs server-side filters from
authenticated claims; client supplied filters are never trusted." Until now
the platform only had `LocalVectorIndex`, an in-memory, vector-only index
that enforced entitlement by filtering results in Python after fetching
every chunk — correct for a small offline fixture, but not a demonstration
of server-side filtering, and not hybrid (no keyword/BM25 component).

## Decision

Add `AzureSearchIndex` (`rag/azure_search.py`) implementing the same
`VectorIndex` protocol `LocalVectorIndex` already satisfies, so
`AuthorizedRetriever` (the entitlement-aware retrieval entry point every
caller uses) is unchanged by which backend is behind it. `VectorIndex.search`
was widened to take both the raw query text and its embedding, not just the
embedding, so a real backend can combine keyword and vector search; a
vector-only implementation is free to ignore the text.

Entitlement filtering is a server-side OData `$filter` built from the
caller's authenticated roles and sent to Azure with every query:

```
allowed_roles/all(r: search.in(r, 'agent.invoke|privacy.read', '|'))
```

This requires every role a chunk declares to be held by the caller —
identical subset semantics to `LocalVectorIndex`'s
`chunk.allowed_roles <= caller_roles`. It fails closed: a caller with no
roles matches nothing (`search.in` against an empty list is never true), and
a role containing the filter's delimiter character is rejected outright
rather than silently misparsed, since `search.in` has no per-element
escaping. There is no code path anywhere that accepts a client-supplied
filter string.

Hybrid retrieval combines Azure's BM25 keyword search (`search_text`) with
vector search (`vector_queries`) in one call; Azure fuses the two rankings
(RRF) automatically. Query and document embeddings are the platform's
existing free, deterministic local hash embedding (`LocalHashEmbedding`,
ADR unnumbered — predates this one), not a hosted embedding model: this
keeps local/CI operation free and offline, and can be swapped for a real
embedding model once Azure OpenAI is live-validated (ADR-006) without
changing `AzureSearchIndex`'s interface.

Index management is deliberately separate from the serving path. The gateway
app only queries the index (`AuthorizedRetriever.retrieve`); a standalone
script, `scripts/ingest_azure_search.py`, creates the index schema and
uploads the bundled policy corpus. This mirrors how a real ingestion
pipeline is normally a separate concern from the serving app, and avoids
needing an async app-startup path purely to populate a search index.

Selection is configuration-driven: `RAG_PROVIDER=local` (default) or
`azure_search`, mirroring the `MODEL_GATEWAY_PROVIDER` /
`CONTENT_SAFETY_PROVIDER` pattern from ADR-006/010.

## Consequences

- `AuthorizedRetriever.retrieve` and `VectorIndex.search` are now `async`,
  the smallest change that lets a real network-backed index sit behind the
  same interface `LocalVectorIndex` already implements. The one production
  caller (`PolicyTools.search`, already `async`) and all local-index tests
  were updated to match; behaviour is otherwise unchanged.
- `RetrievalHit.score` is bounded to `[-1, 1]`, sized around
  `LocalVectorIndex`'s cosine similarity. Azure's hybrid RRF score is a
  different, unbounded scale, so `AzureSearchIndex.search` clamps it rather
  than trusting it to already fit — a live query cannot crash on a
  validation error over a score value that carries no security meaning.
- `AzureSearchIndex` has not been exercised against a live Azure AI Search
  resource in this session — none exists in the current sandbox, and
  Terraform does not yet provision a search index (only the service). Same
  status as the Azure OpenAI and Azure Content Safety adapters: implemented,
  type-checked, unit-tested (filter construction, constructor validation),
  and proven not to make any network call at construction time, but not
  live-validated. `scripts/ingest_azure_search.py` is written but likewise
  unexercised.
- Discovered and fixed while wiring this in: `gateway/__init__.py` eagerly
  re-exported `create_app`, which nothing in the codebase actually imported
  through the package root — every caller already used
  `gateway.app`/`gateway.config` directly. That eager import created a real
  circular import once `rag/factory.py` needed `gateway.config.Settings`
  (`rag` → `gateway` → `gateway.app` → `agents` → `mcp_boundary` → `rag`).
  Removed the dead re-export rather than working around the cycle with a
  local import, since nothing depended on it.

## Alternatives considered

- Keep entitlement filtering client-side (fetch broadly, filter in Python)
  even against Azure AI Search: rejected outright — this is exactly what
  ADR-008 ruled out, and it means a query result set briefly contains
  documents the caller is not entitled to before the client-side filter
  runs.
- Generate real embeddings via Azure OpenAI now: deferred until that
  adapter is live-validated (ADR-006); the local hash embedding is free,
  deterministic and sufficient to prove the hybrid retrieval, filtering and
  citation path end-to-end.
- Populate the index from the serving app at startup, matching
  `build_default_retriever`'s local behaviour: rejected as a layering
  violation (index management is not a serving-path concern) and as the
  only way to avoid adding an async app-startup path just for this.
