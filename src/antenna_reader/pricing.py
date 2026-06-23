"""Token pricing + per-call cost computation, so the app can report exactly what
each API call cost (for a costing model in the pitch).

Rates are USD per 1,000,000 tokens, taken from Anthropic's published pricing.
Two discounts apply to cached input (the PDF is marked `cache_control: ephemeral`):
  - writing to the cache costs 1.25x the normal input rate (a one-time premium),
  - reading from the cache costs 0.10x the normal input rate (the big saving on refines).
"""

# USD per 1,000,000 tokens: {model: {"input": ..., "output": ...}}
PRICES = {
    "claude-opus-4-8":   {"input": 5.0, "output": 25.0},
    "claude-opus-4-7":   {"input": 5.0, "output": 25.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5":  {"input": 1.0, "output": 5.0},
}
_DEFAULT = {"input": 3.0, "output": 15.0}  # assume Sonnet-class if unknown

CACHE_WRITE_MULT = 1.25  # writing the PDF into the 5-min ephemeral cache
CACHE_READ_MULT = 0.10   # reading it back on every refine turn


def price_for(model: str) -> dict:
    return PRICES.get(model, _DEFAULT)


def _field(usage, name: str) -> int:
    """Read a token field from either an SDK usage object or a plain dict."""
    if usage is None:
        return 0
    if isinstance(usage, dict):
        return int(usage.get(name) or 0)
    return int(getattr(usage, name, 0) or 0)


def usage_cost(usage, model: str) -> dict:
    """Turn one API call's `usage` into a token + dollar breakdown.

    Returns a JSON-friendly dict: token counts per category, the model, and the
    total `cost_usd` for this single call.
    """
    p = price_for(model)
    fresh_in = _field(usage, "input_tokens")          # uncached input tokens
    out = _field(usage, "output_tokens")
    cache_write = _field(usage, "cache_creation_input_tokens")
    cache_read = _field(usage, "cache_read_input_tokens")

    cost = (
        fresh_in * p["input"]
        + cache_write * p["input"] * CACHE_WRITE_MULT
        + cache_read * p["input"] * CACHE_READ_MULT
        + out * p["output"]
    ) / 1_000_000.0

    return {
        "model": model,
        "input_tokens": fresh_in,
        "cache_write_tokens": cache_write,
        "cache_read_tokens": cache_read,
        "output_tokens": out,
        "billed_input_tokens": fresh_in + cache_write + cache_read,
        "cost_usd": round(cost, 6),
    }
