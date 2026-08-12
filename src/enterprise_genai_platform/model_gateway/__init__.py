"""Owned model gateway: the single enforcement point for LLM access (ADR-006)."""

from enterprise_genai_platform.model_gateway.contracts import (
    ChatMessage,
    ChatModelProvider,
    ModelBudgetExceeded,
    ModelGatewayError,
    ModelGenerationRequest,
    ModelGenerationResult,
    ModelNotAllowed,
    ModelProviderFailure,
    TokenUsage,
)
from enterprise_genai_platform.model_gateway.factory import build_model_gateway
from enterprise_genai_platform.model_gateway.gateway import ModelGateway

__all__ = [
    "ChatMessage",
    "ChatModelProvider",
    "ModelBudgetExceeded",
    "ModelGateway",
    "ModelGatewayError",
    "ModelGenerationRequest",
    "ModelGenerationResult",
    "ModelNotAllowed",
    "ModelProviderFailure",
    "TokenUsage",
    "build_model_gateway",
]
