"""The single enforcement point for model allowlists, budget and telemetry.

Per ADR-006, this stays a thin, in-repository application component: it owns
policy and observability and delegates inference to a provider adapter. It
never reimplements a provider SDK or an OpenAI-compatible proxy surface.
"""

import asyncio
import time
from collections.abc import Iterable

from enterprise_genai_platform.model_gateway.contracts import (
    ChatModelProvider,
    ModelGenerationRequest,
    ModelGenerationResult,
    ModelProviderFailure,
    TokenUsage,
)
from enterprise_genai_platform.model_gateway.policy import ModelAllowlist, TenantBudgetPolicy
from enterprise_genai_platform.model_gateway.pricing import PricingTable
from enterprise_genai_platform.model_gateway.telemetry import (
    generation_span,
    record_content_safety_findings,
    record_failure,
    record_pii_findings,
    record_success,
)
from enterprise_genai_platform.safety.content_safety import (
    ContentSafetyBlockedError,
    ContentSafetyPolicy,
    ContentSafetyProvider,
)
from enterprise_genai_platform.safety.pii import PiiBlockedError, PiiPolicy, PresidioPiiDetector


class ModelGateway:
    """Enforce allowlist and budget policy, then call the provider under timeout/retry."""

    def __init__(
        self,
        provider: ChatModelProvider,
        *,
        provider_name: str,
        allowlist: ModelAllowlist,
        budget: TenantBudgetPolicy,
        pricing: PricingTable,
        timeout_seconds: float = 20.0,
        max_attempts: int = 2,
        pii_detector: PresidioPiiDetector | None = None,
        pii_policy: PiiPolicy | None = None,
        content_safety_provider: ContentSafetyProvider | None = None,
        content_safety_policy: ContentSafetyPolicy | None = None,
    ) -> None:
        if timeout_seconds <= 0 or max_attempts < 1:
            raise ValueError("Model gateway limits must be positive")
        self._provider = provider
        self._provider_name = provider_name
        self._allowlist = allowlist
        self._budget = budget
        self._pricing = pricing
        self._timeout = timeout_seconds
        self._max_attempts = max_attempts
        self._pii_detector = pii_detector
        self._pii_policy = pii_policy
        self._content_safety_provider = content_safety_provider
        self._content_safety_policy = content_safety_policy

    @property
    def allowed_models(self) -> frozenset[str]:
        return self._allowlist.allowed_models

    async def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
        """Return a policy-checked, cost-attributed completion or fail closed."""
        self._allowlist.check(request.model)
        sanitized_request = self._apply_pii_guard_to_request(request)
        await self._apply_content_safety_guard(
            message.content for message in sanitized_request.messages
        )
        preflight_usage = TokenUsage(
            prompt_tokens=self._estimate_prompt_tokens(sanitized_request),
            completion_tokens=sanitized_request.max_tokens,
        )
        self._budget.check_and_reserve(
            request.tenant, self._pricing.estimate_cost_gbp(request.model, preflight_usage)
        )

        started = time.perf_counter()
        outcome = "error"
        result: ModelGenerationResult | None = None
        with generation_span(sanitized_request, provider=self._provider_name) as span:
            try:
                for attempt in range(1, self._max_attempts + 1):
                    try:
                        async with asyncio.timeout(self._timeout):
                            raw_result = await self._provider.generate(sanitized_request)
                        sanitized_content = self._apply_pii_guard_to_text(raw_result.content)
                        await self._apply_content_safety_guard((sanitized_content,))
                        result = raw_result.model_copy(
                            update={
                                "content": sanitized_content,
                                "estimated_cost_gbp": self._pricing.estimate_cost_gbp(
                                    raw_result.model, raw_result.usage
                                ),
                            }
                        )
                        outcome = "success"
                        return result
                    except TimeoutError:
                        outcome = "timeout"
                    except PiiBlockedError:
                        outcome = "pii_blocked"
                        raise
                    except ContentSafetyBlockedError:
                        outcome = "content_safety_blocked"
                        raise
                    except ModelProviderFailure:
                        outcome = "provider_error"
                        if attempt == self._max_attempts:
                            raise
                raise ModelProviderFailure("Model provider timed out on every attempt")
            finally:
                if outcome == "success" and result is not None:
                    record_success(span, result, tenant=sanitized_request.tenant)
                else:
                    record_failure(
                        span,
                        model=request.model,
                        provider=self._provider_name,
                        outcome=outcome,
                        duration_seconds=time.perf_counter() - started,
                        tenant=request.tenant,
                    )

    @staticmethod
    def _estimate_prompt_tokens(request: ModelGenerationRequest) -> int:
        """A conservative pre-call estimate used only to reserve budget."""
        return max(1, sum(len(message.content) for message in request.messages) // 4)

    def _apply_pii_guard_to_request(
        self, request: ModelGenerationRequest
    ) -> ModelGenerationRequest:
        """Mask or block PII in every message before it reaches a provider."""
        detector, policy = self._pii_detector, self._pii_policy
        if detector is None or policy is None:
            return request
        sanitized_messages = tuple(
            message.model_copy(
                update={"content": self._scan_and_record(detector, policy, message.content)}
            )
            for message in request.messages
        )
        return request.model_copy(update={"messages": sanitized_messages})

    def _apply_pii_guard_to_text(self, text: str) -> str:
        """Mask or block PII in provider-generated content before it is returned."""
        detector, policy = self._pii_detector, self._pii_policy
        if detector is None or policy is None:
            return text
        return self._scan_and_record(detector, policy, text)

    @staticmethod
    def _scan_and_record(detector: PresidioPiiDetector, policy: PiiPolicy, text: str) -> str:
        try:
            scan = detector.scan(text, policy)
        except PiiBlockedError as exc:
            record_pii_findings(exc.entity_types, action="blocked")
            raise
        if scan.findings:
            record_pii_findings((finding.entity_type for finding in scan.findings), action="masked")
        return scan.sanitized_text

    async def _apply_content_safety_guard(self, texts: Iterable[str]) -> None:
        """Block on any text whose severity meets the policy threshold; fails closed."""
        provider, policy = self._content_safety_provider, self._content_safety_policy
        if provider is None or policy is None:
            return
        for text in texts:
            if not text:
                continue
            try:
                async with asyncio.timeout(self._timeout):
                    findings = await provider.check(text)
            except Exception as exc:
                record_content_safety_findings(("_unavailable",), action="provider_error")
                raise ContentSafetyBlockedError(
                    "Content safety check was unavailable; request blocked as a precaution",
                    findings=(),
                ) from exc

            blocked = policy.blocked_findings(findings)
            if blocked:
                record_content_safety_findings(
                    (finding.category for finding in blocked), action="blocked"
                )
                raise ContentSafetyBlockedError(
                    f"Content violates policy: {sorted({finding.category for finding in blocked})}",
                    findings=blocked,
                )
