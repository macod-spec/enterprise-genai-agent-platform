"""Keyless Azure OpenAI adapter authenticated through Entra workload identity.

No API key is ever read from configuration: authentication uses
`DefaultAzureCredential`, which resolves to workload identity federation on
AKS and to the developer's `az login` session locally, consistent with the
platform's no-embedded-credential principle.
"""

import time
from typing import cast

from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider
from openai import AsyncAzureOpenAI
from openai.types.chat import ChatCompletionMessageParam

from enterprise_genai_platform.model_gateway.contracts import (
    ModelGenerationRequest,
    ModelGenerationResult,
    ModelProviderFailure,
    TokenUsage,
)

PROVIDER_NAME = "azure_openai"
_COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"


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
                max_tokens=request.max_tokens,
                temperature=request.temperature,
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
