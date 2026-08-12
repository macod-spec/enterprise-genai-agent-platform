"""Deterministic, free chat adapter for local development and CI."""

from enterprise_genai_platform.model_gateway.contracts import (
    ModelGenerationRequest,
    ModelGenerationResult,
    TokenUsage,
)

PROVIDER_NAME = "mock"
MODEL_NAME = "mock-deterministic"


class MockChatModel:
    """Echo a bounded, deterministic acknowledgement with no network call."""

    async def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
        last_user_message = next(
            (message.content for message in reversed(request.messages) if message.role == "user"),
            "",
        )
        prompt_tokens = sum(max(1, len(message.content.split())) for message in request.messages)
        content = (
            f"[mock-deterministic] Acknowledged {len(last_user_message.split())} word request "
            f"for agent '{request.agent}'."
        )
        usage = TokenUsage(prompt_tokens=prompt_tokens, completion_tokens=len(content.split()))
        return ModelGenerationResult(
            content=content,
            model=MODEL_NAME,
            provider=PROVIDER_NAME,
            usage=usage,
            estimated_cost_gbp=0.0,
            latency_seconds=0.0,
            finish_reason="stop",
        )
