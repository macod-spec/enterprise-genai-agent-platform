"""Bounded LangGraph supervisor routing workflow."""

import logging
from typing import TypedDict, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, ConfigDict, Field

from enterprise_genai_platform.metrics import MODEL_ESTIMATED_COST_GBP, MODEL_TOKENS
from enterprise_genai_platform.models import ModelProvider, RoutingDecision

logger = logging.getLogger(__name__)


class SupervisorState(TypedDict, total=False):
    """Explicit state shared across supervisor graph nodes."""

    query: str
    decision: RoutingDecision
    steps: int
    error_code: str | None


class SupervisorResult(BaseModel):
    """Stable result returned to gateway and evaluation layers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: RoutingDecision
    steps: int = Field(ge=1)
    error_code: str | None = None


class SupervisorWorkflow:
    """Classify a request without permitting model-driven tool execution."""

    def __init__(self, model: ModelProvider, *, max_steps: int = 8) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be at least 1")
        self._model = model
        self._max_steps = max_steps
        self._graph = self._build_graph()

    def _build_graph(
        self,
    ) -> CompiledStateGraph[SupervisorState, None, SupervisorState, SupervisorState]:
        builder = StateGraph(SupervisorState)
        builder.add_node("classify", self._classify)
        builder.add_edge(START, "classify")
        builder.add_edge("classify", END)
        return builder.compile()

    async def _classify(self, state: SupervisorState) -> SupervisorState:
        # This routing-preview path (POST /workflows/route) is a free,
        # deterministic classification step, not a tenant-attributed
        # generation call — it precedes tenant resolution and does not carry
        # tenant context. Labelled "unscoped" rather than a real tenant name
        # so it stays visibly distinct from actual per-tenant spend, which
        # is the metric that matters for quota isolation.
        MODEL_TOKENS.labels("unscoped", "mock", "input").inc(max(1, len(state["query"].split())))
        MODEL_ESTIMATED_COST_GBP.labels("unscoped", "mock").inc(0)
        try:
            decision = await self._model.classify_route(state["query"])
            return {"decision": decision, "steps": state.get("steps", 0) + 1, "error_code": None}
        except Exception:
            logger.exception("supervisor_model_failure")
            return {
                "decision": RoutingDecision(
                    route="human_review",
                    reason="Automated routing was unavailable; manual review is required.",
                    confidence=0.0,
                    requires_human_approval=True,
                ),
                "steps": state.get("steps", 0) + 1,
                "error_code": "MODEL_PROVIDER_FAILURE",
            }

    async def route(self, query: str) -> SupervisorResult:
        """Execute the bounded graph and validate its public result."""
        output = cast(
            SupervisorState,
            await self._graph.ainvoke(
                {"query": query, "steps": 0, "error_code": None},
                config={"recursion_limit": self._max_steps},
            ),
        )
        return SupervisorResult(
            decision=output["decision"],
            steps=output["steps"],
            error_code=output.get("error_code"),
        )
