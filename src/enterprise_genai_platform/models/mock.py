"""Deterministic, free model implementation for local development and CI."""

import re
from typing import cast

from enterprise_genai_platform.models.base import AgentRoute, RoutingDecision

_HIGH_RISK_PATTERNS = (
    re.compile(r"\b(refund|reverse|cancel|release|send|transfer)\b", re.IGNORECASE),
    re.compile(r"[£$€]\s?\d+", re.IGNORECASE),
)
_PAYMENT_TERMS = frozenset(
    {"payment", "transaction", "transfer", "refund", "route", "beneficiary", "failed"}
)
_CUSTOMER_TERMS = frozenset({"customer", "account", "contact", "address", "profile", "preference"})
_POLICY_TERMS = frozenset(
    {"policy", "procedure", "eligible", "eligibility", "rule", "compliance", "limit"}
)


class DeterministicMockModel:
    """Classify requests through explicit rules with no network or model cost."""

    async def classify_route(self, query: str) -> RoutingDecision:
        normalized = query.casefold()
        terms = frozenset(re.findall(r"[a-z]+", normalized))

        if all(pattern.search(query) for pattern in _HIGH_RISK_PATTERNS):
            return RoutingDecision(
                route="human_review",
                reason="A consequential financial action with a stated amount requires approval.",
                confidence=1.0,
                requires_human_approval=True,
            )

        scores = {
            "payments": len(terms & _PAYMENT_TERMS),
            "customer": len(terms & _CUSTOMER_TERMS),
            "policy": len(terms & _POLICY_TERMS),
        }
        highest_score = max(scores.values())
        if highest_score == 0:
            return RoutingDecision(
                route="human_review",
                reason="The request does not match an approved specialist capability.",
                confidence=0.0,
                requires_human_approval=True,
            )

        # A stable priority makes ambiguous CI results reproducible.
        route = next(
            name for name in ("payments", "customer", "policy") if scores[name] == highest_score
        )
        return RoutingDecision(
            route=cast(AgentRoute, route),
            reason=f"The request matched {route} domain terminology.",
            confidence=min(0.5 + (highest_score * 0.2), 0.99),
        )
