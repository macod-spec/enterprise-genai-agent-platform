"""Supervisor-to-specialist NovaBank operations workflow."""

import logging
from typing import Literal, Protocol, TypedDict, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, ConfigDict, Field

from enterprise_genai_platform.agents import CustomerAgent, PaymentsAgent, PolicyAgent
from enterprise_genai_platform.agents.base import AgentResult
from enterprise_genai_platform.mcp_boundary.contracts import CallerContext
from enterprise_genai_platform.models import ModelProvider, RoutingDecision
from enterprise_genai_platform.models.base import AgentRoute
from enterprise_genai_platform.orchestration.supervisor import SupervisorWorkflow

logger = logging.getLogger(__name__)


class Specialist(Protocol):
    async def investigate(self, query: str, caller: CallerContext) -> AgentResult: ...


class OperationsState(TypedDict, total=False):
    query: str
    decision: RoutingDecision
    result: AgentResult
    steps: int
    subject: str
    roles: frozenset[str]
    request_id: str


class OperationsResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: RoutingDecision
    result: AgentResult
    steps: int = Field(ge=2)


class OperationsWorkflow:
    """Route only to explicitly registered specialists and execute read-only investigation."""

    def __init__(
        self,
        model: ModelProvider,
        customer: CustomerAgent,
        payments: PaymentsAgent,
        policy: PolicyAgent,
        *,
        max_steps: int = 8,
    ) -> None:
        self._supervisor = SupervisorWorkflow(model, max_steps=max_steps)
        self._customer = customer
        self._payments = payments
        self._policy = policy
        self._max_steps = max_steps
        self._graph = self._build_graph()

    def _build_graph(
        self,
    ) -> CompiledStateGraph[OperationsState, None, OperationsState, OperationsState]:
        builder = StateGraph(OperationsState)
        builder.add_node("classify", self._classify)
        builder.add_node("customer", self._customer_node)
        builder.add_node("payments", self._payments_node)
        builder.add_node("policy", self._policy_node)
        builder.add_node("human_review", self._human_review_node)
        builder.add_edge(START, "classify")
        builder.add_conditional_edges(
            "classify",
            self._selected_route,
            {
                "customer": "customer",
                "payments": "payments",
                "policy": "policy",
                "human_review": "human_review",
            },
        )
        for node in ("customer", "payments", "policy", "human_review"):
            builder.add_edge(node, END)
        return builder.compile()

    async def _classify(self, state: OperationsState) -> OperationsState:
        routed = await self._supervisor.route(state["query"])
        return {"decision": routed.decision, "steps": state.get("steps", 0) + routed.steps}

    @staticmethod
    def _selected_route(state: OperationsState) -> AgentRoute:
        return state["decision"].route

    async def _run_specialist(
        self,
        specialist: Specialist,
        agent: Literal["customer", "payments", "policy"],
        state: OperationsState,
    ) -> OperationsState:
        caller = CallerContext(
            subject=state["subject"],
            roles=state["roles"],
            agent=agent,
            request_id=state["request_id"],
        )
        try:
            result = await specialist.investigate(state["query"], caller)
        except Exception:
            logger.exception("specialist_agent_failure")
            result = AgentResult(
                agent="human_review",
                summary="The specialist was unavailable; manual review is required.",
                requires_human_approval=True,
                error_code="SPECIALIST_FAILURE",
            )
        return {"result": result, "steps": state.get("steps", 0) + 1}

    async def _customer_node(self, state: OperationsState) -> OperationsState:
        return await self._run_specialist(self._customer, "customer", state)

    async def _payments_node(self, state: OperationsState) -> OperationsState:
        return await self._run_specialist(self._payments, "payments", state)

    async def _policy_node(self, state: OperationsState) -> OperationsState:
        return await self._run_specialist(self._policy, "policy", state)

    @staticmethod
    async def _human_review_node(state: OperationsState) -> OperationsState:
        return {
            "result": AgentResult(
                agent="human_review",
                summary=state["decision"].reason,
                requires_human_approval=True,
            ),
            "steps": state.get("steps", 0) + 1,
        }

    async def investigate(
        self,
        query: str,
        *,
        subject: str,
        roles: frozenset[str],
        request_id: str,
    ) -> OperationsResult:
        output = cast(
            OperationsState,
            await self._graph.ainvoke(
                {
                    "query": query,
                    "steps": 0,
                    "subject": subject,
                    "roles": roles,
                    "request_id": request_id,
                },
                config={"recursion_limit": self._max_steps},
            ),
        )
        return OperationsResult(
            decision=output["decision"],
            result=output["result"],
            steps=output["steps"],
        )
