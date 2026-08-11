"""Governed skill-definition schema."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Owner(StrictModel):
    team: str = Field(pattern=r"^[a-z][a-z0-9-]{2,49}$")
    contact: str = Field(pattern=r"^[a-z0-9-]+@novabank\.example$")


class ModelPolicy(StrictModel):
    provider: Literal["mock"]
    model: str
    max_input_tokens: int = Field(ge=100, le=32_000)
    max_output_tokens: int = Field(ge=50, le=8_000)


class ApprovalPolicy(StrictModel):
    required_for: tuple[str, ...]
    approver_role: str


class SLOPolicy(StrictModel):
    availability_percent: float = Field(ge=90, le=100)
    latency_p95_ms: int = Field(gt=0, le=60_000)


class EvaluationPolicy(StrictModel):
    suite: str
    minimum_score: float = Field(ge=0, le=1)


class SkillDefinition(StrictModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    description: str = Field(min_length=10, max_length=500)
    owner: Owner
    agent: Literal["customer", "payments", "policy"]
    model: ModelPolicy
    allowed_tools: tuple[str, ...]
    data_classification: Literal["internal", "confidential"]
    approval: ApprovalPolicy
    slo: SLOPolicy
    evaluation: EvaluationPolicy
    governance_state: Literal["draft", "approved", "deprecated"]
