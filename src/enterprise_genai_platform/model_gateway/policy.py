"""Deny-by-default model allowlist and per-tenant spend ceiling enforcement."""

import time
from collections import defaultdict, deque

from enterprise_genai_platform.model_gateway.contracts import ModelBudgetExceeded, ModelNotAllowed


class ModelAllowlist:
    """Reject any model name that has not been explicitly approved."""

    def __init__(self, allowed_models: frozenset[str]) -> None:
        if not allowed_models:
            raise ValueError("At least one model must be allowlisted")
        self._allowed = allowed_models

    @property
    def allowed_models(self) -> frozenset[str]:
        return self._allowed

    def check(self, model: str) -> None:
        if model not in self._allowed:
            raise ModelNotAllowed(f"Model '{model}' is not on the governed allowlist")


class TenantBudgetPolicy:
    """Track rolling GBP spend per tenant and fail closed once a ceiling is reached.

    This is an in-process, best-effort control suitable for a single gateway
    replica. A durable, cross-replica ledger is required before this policy
    can be relied on for hard multi-tenant cost enforcement in production.
    """

    def __init__(self, *, daily_ceiling_gbp: float, window_seconds: int = 86_400) -> None:
        if daily_ceiling_gbp <= 0:
            raise ValueError("daily_ceiling_gbp must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self._ceiling = daily_ceiling_gbp
        self._window = window_seconds
        self._spend: dict[str, deque[tuple[float, float]]] = defaultdict(deque)

    def check_and_reserve(self, tenant: str, estimated_cost_gbp: float) -> None:
        """Raise ModelBudgetExceeded if the projected spend would exceed the ceiling."""
        now = time.monotonic()
        ledger = self._spend[tenant]
        while ledger and ledger[0][0] <= now - self._window:
            ledger.popleft()
        spent = sum(cost for _, cost in ledger)
        if spent + estimated_cost_gbp > self._ceiling:
            raise ModelBudgetExceeded(
                f"Tenant '{tenant}' would exceed its {self._ceiling:g} GBP budget window"
            )
        ledger.append((now, estimated_cost_gbp))

    def spent_gbp(self, tenant: str) -> float:
        now = time.monotonic()
        ledger = self._spend[tenant]
        while ledger and ledger[0][0] <= now - self._window:
            ledger.popleft()
        return round(sum(cost for _, cost in ledger), 8)
