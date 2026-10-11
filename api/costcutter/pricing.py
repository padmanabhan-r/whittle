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

# OpenAI: list prices as published in mid-2026, taken from third-party price listings
# and not yet checked against OpenAI's own page. OpenAI charges no surcharge to write
# a cache entry, so cache write is the input price.
RATES.update({
    "gpt-5.5": ModelRates(5.0, 30.0, 0.50, 5.0),
    "gpt-5.4": ModelRates(2.5, 15.0, 0.25, 2.5),
    "gpt-5.4-mini": ModelRates(0.75, 4.5, 0.075, 0.75),
    "gpt-5.4-nano": ModelRates(0.20, 1.25, 0.02, 0.20),
    "gpt-5-mini": ModelRates(0.25, 2.0, 0.025, 0.25),
    "gpt-5-nano": ModelRates(0.05, 0.40, 0.005, 0.05),
})

DEFAULT_RATES = ModelRates(4.0, 20.0, 0.20, 5.0)


def known(model: str) -> bool:
    """Whether this model has a price here. An unknown model is charged at the top rate, so its cost is an upper estimate."""
    return _match(model) is not None


def _match(model: str) -> str | None:
    if model in RATES:
        return model
    # A dated or suffixed id ("gpt-5.4-mini-2026-03-01") prices as the longest name it starts with.
    best = max((name for name in RATES if model.startswith(name + "-")), key=len, default=None)
    return best


def rates_for(model: str) -> ModelRates:
    name = _match(model)
    return RATES[name] if name else DEFAULT_RATES


def cost_usd(
    model: str,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    """`input_tokens` is the uncached input only, as both providers' usage is recorded here:
    cache reads and writes are counted in their own fields and priced at their own rates."""
    r = rates_for(model)
    cost = (
        input_tokens * r.input_per_million
        + output_tokens * r.output_per_million
        + cache_read_tokens * (r.cache_read_per_million or r.input_per_million * 0.1)
        + cache_write_tokens * (r.cache_write_per_million or r.input_per_million * 1.25)
    ) / 1_000_000
    return round(cost, 8)
