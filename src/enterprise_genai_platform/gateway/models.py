"""Versioned API response contracts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from enterprise_genai_platform.agents.base import AgentResult
from enterprise_genai_platform.models import RoutingDecision
from enterprise_genai_platform.skills.models import SkillDefinition


class StrictResponse(BaseModel):
    """Base response that rejects accidental schema drift."""

    model_config = ConfigDict(extra="forbid")


class HealthResponse(StrictResponse):
    status: Literal["ok"] = "ok"


class ReadinessResponse(StrictResponse):
    status: Literal["ready"] = "ready"
    checks: dict[str, Literal["ready"]]


class PlatformInfoResponse(StrictResponse):
    name: str
    environment: str
    authenticated_subject: str


class RouteRequest(StrictResponse):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(min_length=1, max_length=2_000)


class RouteResponse(StrictResponse):
    decision: RoutingDecision
    steps: int
    error_code: str | None = None


class InvestigationResponse(StrictResponse):
    decision: RoutingDecision
    result: AgentResult
    steps: int
    approval_id: str | None = None


class SkillListResponse(StrictResponse):
    skills: tuple[SkillDefinition, ...]
