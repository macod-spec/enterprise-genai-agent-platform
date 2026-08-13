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

    Ceilings are per-tenant (each tenant's config bundle sets its own
    token_budget_gbp), never a single number shared across tenants — that
    would let one tenant's usage crowd out another's, the exact quota
    leakage the multi-tenancy design exists to prevent. default_ceiling_gbp
    exists only for callers with no tenant bundle at all (mock/local-dev
    paths); any tenant present in `ceilings` always uses its own value.

    This is an in-process, best-effort control suitable for a single gateway
    replica. A durable, cross-replica ledger is required before this policy
    can be relied on for hard multi-tenant cost enforcement in production.
    """

    def __init__(
        self,
        *,
        ceilings: dict[str, float] | None = None,
        default_ceiling_gbp: float | None = None,
        window_seconds: int = 86_400,
    ) -> None:
        if not ceilings and default_ceiling_gbp is None:
            raise ValueError("At least one of ceilings or default_ceiling_gbp is required")
        if any(value <= 0 for value in (ceilings or {}).values()):
            raise ValueError("Every ceiling must be positive")
        if default_ceiling_gbp is not None and default_ceiling_gbp <= 0:
            raise ValueError("default_ceiling_gbp must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self._ceilings = dict(ceilings or {})
        self._default_ceiling = default_ceiling_gbp
        self._window = window_seconds
        self._spend: dict[str, deque[tuple[float, float]]] = defaultdict(deque)

    def _ceiling_for(self, tenant: str) -> float:
        ceiling = self._ceilings.get(tenant, self._default_ceiling)
        if ceiling is None:
            raise ModelBudgetExceeded(f"Tenant '{tenant}' has no configured budget ceiling")
        return ceiling

    def check_and_reserve(self, tenant: str, estimated_cost_gbp: float) -> None:
        """Raise ModelBudgetExceeded if the projected spend would exceed the ceiling."""
        ceiling = self._ceiling_for(tenant)
        now = time.monotonic()
        ledger = self._spend[tenant]
        while ledger and ledger[0][0] <= now - self._window:
            ledger.popleft()
        spent = sum(cost for _, cost in ledger)
        if spent + estimated_cost_gbp > ceiling:
            raise ModelBudgetExceeded(
                f"Tenant '{tenant}' would exceed its {ceiling:g} GBP budget window"
            )
        ledger.append((now, estimated_cost_gbp))

    def spent_gbp(self, tenant: str) -> float:
        now = time.monotonic()
        ledger = self._spend[tenant]
        while ledger and ledger[0][0] <= now - self._window:
            ledger.popleft()
        return round(sum(cost for _, cost in ledger), 8)
