"""Provider-neutral chat generation contracts owned by the model gateway."""

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

ChatRole = Literal["system", "user", "assistant"]


class ModelGatewayError(RuntimeError):
    """Base exception safe for mapping to a controlled agent or HTTP result."""


class ModelNotAllowed(ModelGatewayError):
    """Raised when a request names a model outside the governed allowlist."""


class ModelBudgetExceeded(ModelGatewayError):
    """Raised when a tenant or agent has exhausted its configured spend ceiling."""


class ModelProviderFailure(ModelGatewayError):
    """Raised when every attempt against the underlying provider has failed."""


class ChatMessage(BaseModel):
    """One turn in a bounded chat completion request."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    role: ChatRole
    content: str = Field(min_length=1, max_length=8_000)


class TokenUsage(BaseModel):
    """Token accounting returned by every provider adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class ModelGenerationRequest(BaseModel):
    """A validated, tenant-attributed request into the model gateway."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    model: str = Field(min_length=1, max_length=200)
    messages: tuple[ChatMessage, ...] = Field(min_length=1, max_length=50)
    tenant: str = Field(min_length=1, max_length=200)
    agent: str = Field(min_length=1, max_length=100)
    max_tokens: int = Field(default=512, ge=1, le=4_096)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)


class ModelGenerationResult(BaseModel):
    """A validated response with the telemetry every caller needs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    content: str
    model: str
    provider: str
    usage: TokenUsage
    estimated_cost_gbp: float = Field(ge=0.0)
    latency_seconds: float = Field(ge=0.0)
    finish_reason: str


class ChatModelProvider(Protocol):
    """Minimal capability every model gateway adapter must implement."""

    async def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
        """Return a validated completion or raise ModelProviderFailure."""
        ...
