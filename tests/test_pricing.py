from antenna_reader.pricing import price_for, usage_cost


def test_sonnet_basic_cost():
    # 10k fresh input @ $3/M + 2k output @ $15/M = 0.03 + 0.03 = 0.06
    c = usage_cost({"input_tokens": 10_000, "output_tokens": 2_000}, "claude-sonnet-4-6")
    assert c["cost_usd"] == round((10_000 * 3 + 2_000 * 15) / 1_000_000, 6)
    assert c["cost_usd"] == 0.06
    assert c["billed_input_tokens"] == 10_000


def test_cache_discounts_make_refines_cheap():
    # The PDF (50k tok) read from cache costs 10% of input; a small fresh refine instruction.
    c = usage_cost({"input_tokens": 200, "cache_read_input_tokens": 50_000,
                    "output_tokens": 1_500}, "claude-sonnet-4-6")
    expected = (200 * 3 + 50_000 * 3 * 0.10 + 1_500 * 15) / 1_000_000
    assert c["cost_usd"] == round(expected, 6)
    # Reading the cached PDF (15k) is far cheaper than re-sending it fresh (45k).
    assert 50_000 * 3 * 0.10 < 50_000 * 3


def test_cache_write_premium():
    c = usage_cost({"cache_creation_input_tokens": 50_000, "output_tokens": 0},
                   "claude-sonnet-4-6")
    assert c["cost_usd"] == round(50_000 * 3 * 1.25 / 1_000_000, 6)


def test_haiku_is_a_third_of_sonnet_on_input():
    assert price_for("claude-haiku-4-5")["input"] * 3 == price_for("claude-sonnet-4-6")["input"]


def test_unknown_model_falls_back_and_handles_none_usage():
    assert usage_cost(None, "made-up")["cost_usd"] == 0.0
    assert price_for("made-up")["input"] == 3.0
