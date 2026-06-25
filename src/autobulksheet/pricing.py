"""Token pricing + per-call cost computation, so the app can report exactly what each API
call cost (shown in the GUI after each run).

Rates are USD per 1,000,000 tokens, from Anthropic's published pricing.
"""

# USD per 1,000,000 tokens: {model: {"input": ..., "output": ...}}
PRICES = {
    "claude-opus-4-8":   {"input": 5.0, "output": 25.0},
    "claude-opus-4-7":   {"input": 5.0, "output": 25.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5":  {"input": 1.0, "output": 5.0},
}
_DEFAULT = {"input": 3.0, "output": 15.0}  # assume Sonnet-class if unknown


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

    Returns a JSON-friendly dict: input/output token counts, the model, and the total
    `cost_usd` for this single call.
    """
    p = price_for(model)
    inp = _field(usage, "input_tokens")
    out = _field(usage, "output_tokens")
    cost = (inp * p["input"] + out * p["output"]) / 1_000_000.0
    return {
        "model": model,
        "input_tokens": inp,
        "output_tokens": out,
        "cost_usd": round(cost, 6),
    }
