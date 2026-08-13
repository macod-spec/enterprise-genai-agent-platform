"""Keyless Azure OpenAI adapter authenticated through Entra workload identity.

No API key is ever read from configuration: authentication uses
`DefaultAzureCredential`, which resolves to workload identity federation on
AKS and to the developer's `az login` session locally, consistent with the
platform's no-embedded-credential principle.
"""

import time
from typing import cast

from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider
from openai import AsyncAzureOpenAI, omit
from openai.types.chat import ChatCompletionMessageParam

from enterprise_genai_platform.model_gateway.contracts import (
    ModelGenerationRequest,
    ModelGenerationResult,
    ModelProviderFailure,
    TokenUsage,
)

PROVIDER_NAME = "azure_openai"
_COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"
# Reasoning-family models (o1, o3, o4-*, gpt-5*) reject any explicit temperature
# value other than their default (1) with a 400 unsupported_value error — confirmed
# against a live gpt-5-nano deployment, not a documentation guess. There is no
# capability flag in the deployment/model metadata that distinguishes this, so the
# model name prefix is the only signal available.
_REASONING_MODEL_PREFIXES = ("o1", "o3", "o4", "gpt-5")


def _is_reasoning_model(model: str) -> bool:
    return model.startswith(_REASONING_MODEL_PREFIXES)


class AzureOpenAIChatModel:
    """Call an Azure OpenAI chat completions deployment over async HTTPS."""

    def __init__(
        self,
        *,
        endpoint: str,
        api_version: str,
        timeout_seconds: float,
        credential: DefaultAzureCredential | None = None,
    ) -> None:
        if not endpoint or not api_version:
            raise ValueError("Azure OpenAI endpoint and api_version are required")
        token_provider = get_bearer_token_provider(
            credential or DefaultAzureCredential(), _COGNITIVE_SERVICES_SCOPE
        )
        self._client = AsyncAzureOpenAI(
            azure_endpoint=endpoint,
            api_version=api_version,
            azure_ad_token_provider=token_provider,
            timeout=timeout_seconds,
        )

    async def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
        started = time.perf_counter()
        # Reasoning-family models reject an explicit temperature outright (400
        # unsupported_value); `omit` drops the parameter from the request entirely
        # rather than sending a value the API will refuse.
        temperature = omit if _is_reasoning_model(request.model) else request.temperature
        try:
            response = await self._client.chat.completions.create(
                model=request.model,
                messages=cast(
                    list[ChatCompletionMessageParam],
                    [
                        {"role": message.role, "content": message.content}
                        for message in request.messages
                    ],
                ),
                # max_completion_tokens, not the deprecated max_tokens: reasoning-family
                # models reject max_tokens outright with a 400 "unsupported_parameter"
                # error. max_completion_tokens is accepted by both reasoning and
                # non-reasoning chat completion models.
                max_completion_tokens=request.max_tokens,
                temperature=temperature,
            )
        except Exception as exc:
            raise ModelProviderFailure("Azure OpenAI request failed") from exc

        choice = response.choices[0] if response.choices else None
        if choice is None or choice.message.content is None or response.usage is None:
            raise ModelProviderFailure("Azure OpenAI returned no usable completion")

        usage = TokenUsage(
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
        )
        return ModelGenerationResult(
            content=choice.message.content,
            model=response.model,
            provider=PROVIDER_NAME,
            usage=usage,
            estimated_cost_gbp=0.0,  # populated by the gateway from the governed pricing table
            latency_seconds=time.perf_counter() - started,
            finish_reason=choice.finish_reason,
        )
