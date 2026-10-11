from costcutter.pricing import cost_usd


def test_cost_increases_with_output_tokens():
    low = cost_usd("claude-sonnet-5-5", input_tokens=1000, output_tokens=10)
    high = cost_usd("claude-sonnet-5-5", input_tokens=1000, output_tokens=500)
    assert high > low


def test_cache_read_cheaper_than_fresh_input():
    fresh = cost_usd("claude-sonnet-5-5", input_tokens=5000, output_tokens=0)
    cached = cost_usd(
        "claude-sonnet-5-5",
        input_tokens=1000,
        output_tokens=0,
        cache_read_tokens=4000,
    )
    assert cached < fresh


def test_uncached_input_is_still_charged_when_the_cache_is_hit():
    """input_tokens is the uncached part; a cache hit must not make it free."""
    only_cache = cost_usd("claude-sonnet-5-5", cache_read_tokens=1878)
    with_input = cost_usd("claude-sonnet-5-5", input_tokens=137, cache_read_tokens=1878)
    assert round(with_input - only_cache, 8) == round(137 * 2.0 / 1_000_000, 8)


def test_dated_model_ids_use_their_family_price():
    from costcutter.pricing import known

    assert cost_usd("gpt-5.4-mini-2026-03-01", input_tokens=1_000_000) == 0.75
    assert known("gpt-5.4-mini-2026-03-01") and not known("some-new-model")
