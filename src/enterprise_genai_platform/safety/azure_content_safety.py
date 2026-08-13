"""Keyless Azure AI Content Safety adapter authenticated through Entra workload identity.

No API key is ever read from configuration: authentication uses
`DefaultAzureCredential`, consistent with the Azure OpenAI adapter
(`model_gateway/adapters/azure_openai.py`).
"""

from typing import cast

from azure.ai.contentsafety.aio import ContentSafetyClient
from azure.ai.contentsafety.models import AnalyzeTextOptions
from azure.identity.aio import DefaultAzureCredential

from enterprise_genai_platform.safety.content_safety import (
    ContentSafetyCategory,
    ContentSafetyFinding,
)


class AzureContentSafetyProvider:
    """Call Azure AI Content Safety's text analysis endpoint over async HTTPS."""

    def __init__(
        self,
        *,
        endpoint: str,
        credential: DefaultAzureCredential | None = None,
    ) -> None:
        if not endpoint:
            raise ValueError("Azure Content Safety endpoint is required")
        self._client = ContentSafetyClient(endpoint, credential or DefaultAzureCredential())

    async def check(self, text: str) -> tuple[ContentSafetyFinding, ...]:
        result = await self._client.analyze_text(AnalyzeTextOptions(text=text))
        return tuple(
            ContentSafetyFinding(
                category=cast(ContentSafetyCategory, analysis.category),
                # A missing severity is treated as maximum severity, not zero:
                # the platform must fail closed on an ambiguous safety signal.
                severity=analysis.severity if analysis.severity is not None else 7,
            )
            for analysis in result.categories_analysis
        )
