"""Per-model token prices (USD per million tokens) for spend caps and estimates."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelRates:
    input_per_million: float
    output_per_million: float
    cache_read_per_million: float | None = None
    cache_write_per_million: float | None = None


# Anthropic's first-party rate card, checked 11 October 2026. Cache read is the
# published read price; cache write is the 5-minute write at 1.25x input.
# Haiku 5.5 is priced for prompts up to 100K tokens. Unknown models use the
# Opus rate so a cap errs on the safe side.
RATES: dict[str, ModelRates] = {
    "claude-opus-5-5": ModelRates(4.0, 20.0, 0.20, 5.0),
    "claude-sonnet-5-5": ModelRates(2.0, 10.0, 0.20, 2.5),
    "claude-haiku-5-5": ModelRates(0.10, 0.50, 0.01, 0.125),
    "claude-opus-5": ModelRates(5.0, 25.0, 0.50, 6.25),
    "claude-sonnet-5": ModelRates(2.0, 10.0, 0.20, 2.5),
    "claude-sonnet-4-6": ModelRates(3.0, 15.0, 0.30, 3.75),
    "claude-haiku-4-5": ModelRates(1.0, 5.0, 0.10, 1.25),
    "claude-sonnet-4-20250514": ModelRates(3.0, 15.0, 0.30, 3.75),
}

DEFAULT_RATES = ModelRates(4.0, 20.0, 0.20, 5.0)


def rates_for(model: str) -> ModelRates:
    return RATES.get(model, DEFAULT_RATES)


def cost_usd(
    model: str,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    r = rates_for(model)
    billable_input = max(0, input_tokens - cache_read_tokens - cache_write_tokens)
    cost = (
        billable_input * r.input_per_million
        + output_tokens * r.output_per_million
        + cache_read_tokens * (r.cache_read_per_million or r.input_per_million * 0.1)
        + cache_write_tokens * (r.cache_write_per_million or r.input_per_million * 1.25)
    ) / 1_000_000
    return round(cost, 8)
