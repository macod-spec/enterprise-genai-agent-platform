"""Deterministic GBP cost estimation for governed model usage.

Prices are illustrative list-price approximations for demonstration and cost
telemetry only; they are not a substitute for the Azure invoice or an
organisation-specific enterprise agreement rate.
"""

from dataclasses import dataclass

from enterprise_genai_platform.model_gateway.contracts import TokenUsage


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """List price per 1,000 tokens, in GBP, for one governed model."""

    prompt_price_per_1k_gbp: float
    completion_price_per_1k_gbp: float


# The mock provider is intentionally free so local development and CI incur
# no cost. Real provider prices are approximate and should be reviewed
# against the current Azure OpenAI GBP price list before use in cost reports.
DEFAULT_PRICING: dict[str, ModelPrice] = {
    "mock-deterministic": ModelPrice(0.0, 0.0),
    "gpt-4o-mini": ModelPrice(0.00012, 0.00048),
    "gpt-4o": ModelPrice(0.0020, 0.0080),
}


class PricingTable:
    """Look up per-model prices with a safe, non-zero fallback for unknown models."""

    def __init__(self, prices: dict[str, ModelPrice] | None = None) -> None:
        self._prices = dict(prices) if prices is not None else dict(DEFAULT_PRICING)

    def estimate_cost_gbp(self, model: str, usage: TokenUsage) -> float:
        price = self._prices.get(model)
        if price is None:
            # An unpriced model must never silently report zero cost.
            price = ModelPrice(0.001, 0.002)
        cost = (usage.prompt_tokens / 1_000) * price.prompt_price_per_1k_gbp
        cost += (usage.completion_tokens / 1_000) * price.completion_price_per_1k_gbp
        return round(cost, 8)
