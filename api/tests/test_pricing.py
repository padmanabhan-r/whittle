from costcutter.pricing import cost_usd


def test_cost_increases_with_output_tokens():
    low = cost_usd("claude-sonnet-5-5", input_tokens=1000, output_tokens=10)
    high = cost_usd("claude-sonnet-5-5", input_tokens=1000, output_tokens=500)
    assert high > low


def test_cache_read_cheaper_than_fresh_input():
    fresh = cost_usd("claude-sonnet-5-5", input_tokens=5000, output_tokens=0)
    cached = cost_usd(
        "claude-sonnet-5-5",
        input_tokens=5000,
        output_tokens=0,
        cache_read_tokens=4000,
    )
    assert cached < fresh
