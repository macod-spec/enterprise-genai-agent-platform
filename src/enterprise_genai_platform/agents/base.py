"""Shared, validated specialist-agent contracts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AgentName = Literal["customer", "payments", "policy", "human_review"]


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1, max_length=100)
    source_type: Literal["customer", "account", "transaction", "policy"]
    detail: str = Field(min_length=1, max_length=1_000)


class AgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agent: AgentName
    summary: str = Field(min_length=1, max_length=2_000)
    evidence: tuple[Evidence, ...] = ()
    requires_human_approval: bool = False
    error_code: str | None = None
