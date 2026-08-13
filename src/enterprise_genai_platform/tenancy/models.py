"""Validated tenant config bundle schema.

Every field here is deliberately closed-vocabulary or bounded (Literal,
Field constraints) rather than a bare string, so a malformed bundle fails
to load at startup instead of degrading quietly at request time.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ModelTier = Literal["cheap", "mid", "strong"]
RiskTier = Literal["low", "medium", "high"]


class ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class MemoryPolicy(ImmutableModel):
    """What a tenant's conversational/approval state retains, and for how long."""

    approval_state_ttl_days: int = Field(ge=1, le=365)
    persists: tuple[str, ...] = Field(min_length=1)
    does_not_persist: tuple[str, ...] = Field(min_length=1)


class TenantBundle(ImmutableModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    system_prompt: str = Field(min_length=1, max_length=2_000)
    allowed_skills: frozenset[str] = Field(min_length=1)
    model_tier: ModelTier
    memory_policy: MemoryPolicy
    entitlements: frozenset[str] = Field(min_length=1)
    token_budget_gbp: float = Field(gt=0, le=10_000)
    risk_tier: RiskTier
    cost_centre: str = Field(min_length=1, max_length=100)
