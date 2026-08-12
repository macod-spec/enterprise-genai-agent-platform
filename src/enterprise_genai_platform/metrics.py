"""Low-cardinality Prometheus metrics with no request or customer content labels."""

from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter(
    "agent_platform_http_requests_total",
    "Gateway HTTP requests",
    ("method", "route", "status"),
)
HTTP_DURATION = Histogram(
    "agent_platform_http_request_duration_seconds",
    "Gateway HTTP request latency",
    ("method", "route"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
WORKFLOW_COMPLETIONS = Counter(
    "agent_platform_workflow_completions_total",
    "Completed workflow routes and outcomes",
    ("route", "agent", "approval_required", "error_code"),
)
WORKFLOW_DURATION = Histogram(
    "agent_platform_workflow_duration_seconds",
    "End-to-end workflow latency",
    ("route",),
)
MCP_CALLS = Counter(
    "agent_platform_mcp_calls_total",
    "Governed MCP calls",
    ("tool", "outcome"),
)
MCP_DURATION = Histogram(
    "agent_platform_mcp_duration_seconds",
    "Governed MCP call latency",
    ("tool",),
)
RAG_RETRIEVALS = Counter(
    "agent_platform_rag_retrievals_total",
    "Authorized RAG retrieval operations",
    ("result",),
)
RAG_HITS = Histogram(
    "agent_platform_rag_hits",
    "Number of authorized RAG hits",
    buckets=(0, 1, 2, 3, 5),
)
MODEL_TOKENS = Counter(
    "agent_platform_model_tokens_total",
    "Estimated tokens processed by provider and direction",
    ("provider", "direction"),
)
MODEL_ESTIMATED_COST_GBP = Counter(
    "agent_platform_model_estimated_cost_gbp_total",
    "Estimated model cost in GBP; deterministic mock remains zero",
    ("provider",),
)
PENDING_APPROVALS = Gauge(
    "agent_platform_pending_approvals",
    "Human approvals created minus decisions in this process",
)


def safe_error_code(value: str | None) -> str:
    """Return one bounded label value; never pass exception text into metrics."""
    return (
        value
        if value
        in {
            "none",
            "MODEL_PROVIDER_FAILURE",
            "SPECIALIST_FAILURE",
            "CUSTOMER_ID_REQUIRED",
            "CUSTOMER_TOOL_FAILURE",
            "TRANSACTION_ID_REQUIRED",
            "PAYMENT_TOOL_FAILURE",
            "CUSTOMER_TRANSACTION_MISMATCH",
            "POLICY_TOOL_FAILURE",
            "POLICY_NOT_FOUND",
        }
        else "other"
    )
