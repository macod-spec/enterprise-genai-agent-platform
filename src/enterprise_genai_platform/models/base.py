"""Provider-neutral model contracts used by agent workflows."""

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

AgentRoute = Literal["customer", "payments", "policy", "human_review"]


class RoutingDecision(BaseModel):
    """Validated structured output from a supervisor model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    route: AgentRoute
    reason: str = Field(min_length=1, max_length=300)
    confidence: float = Field(ge=0.0, le=1.0)
    requires_human_approval: bool = False


class ModelProvider(Protocol):
    """Minimal model capability required by the supervisor."""

    async def classify_route(self, query: str) -> RoutingDecision:
        """Return a validated route without executing any tool or side effect."""
        ...
