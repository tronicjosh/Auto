from autobulksheet.pricing import price_for, usage_cost


def test_sonnet_basic_cost():
    # 10k input @ $3/M + 2k output @ $15/M = 0.03 + 0.03 = 0.06
    c = usage_cost({"input_tokens": 10_000, "output_tokens": 2_000}, "claude-sonnet-4-6")
    assert c["cost_usd"] == round((10_000 * 3 + 2_000 * 15) / 1_000_000, 6)
    assert c["cost_usd"] == 0.06
    assert c["input_tokens"] == 10_000 and c["output_tokens"] == 2_000


def test_haiku_is_a_third_of_sonnet_on_input():
    assert price_for("claude-haiku-4-5")["input"] * 3 == price_for("claude-sonnet-4-6")["input"]


def test_unknown_model_falls_back_and_handles_none_usage():
    assert usage_cost(None, "made-up")["cost_usd"] == 0.0
    assert price_for("made-up")["input"] == 3.0
