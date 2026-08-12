"""Versioned API response contracts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from enterprise_genai_platform.agents.base import AgentResult
from enterprise_genai_platform.model_gateway import ChatMessage, TokenUsage
from enterprise_genai_platform.models import RoutingDecision
from enterprise_genai_platform.rag.models import Citation
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


class ModelGenerateRequest(StrictResponse):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    model: str = Field(min_length=1, max_length=200)
    messages: tuple[ChatMessage, ...] = Field(min_length=1, max_length=50)
    max_tokens: int = Field(default=512, ge=1, le=4_096)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)


class ModelGenerateResponse(StrictResponse):
    content: str
    model: str
    provider: str
    usage: TokenUsage
    estimated_cost_gbp: float
    finish_reason: str


class RagAnswerRequest(StrictResponse):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(min_length=1, max_length=500)


class RagAnswerResponse(StrictResponse):
    answer: str
    citations: tuple[Citation, ...]
    term_overlap_score: float
    citations_found: tuple[str, ...]
    fabricated_citations: tuple[str, ...]
    is_grounded: bool
