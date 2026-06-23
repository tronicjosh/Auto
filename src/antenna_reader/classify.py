"""The router pass: classify an antenna datasheet into one of the workflow's profiles.

A cheap, fast model (Haiku by default) reads the PDF and the router prompt and names the
antenna type. We map its answer to one of the declared profiles by keyword, preferring the
first line (where the router prompt asks it to put the type). If nothing matches, the type is
left unset and the user picks it on the confirmation step.
"""

import base64
import os

import anthropic

from .config import DEFAULT_CLASSIFY_MODEL
from .extract import ExtractionError
from .pricing import usage_cost

_CLASSIFY_MAX_TOKENS = 300


def _match_profile(text: str, profiles: list):
    """Map the router's free-text answer to a profile (key, label). Prefer the first line."""
    stripped = text.strip()
    first = stripped.splitlines()[0].lower() if stripped else ""
    full = stripped.lower()
    for scope in (first, full):
        best, best_pos = None, len(scope) + 1
        for p in profiles:
            for needle in (p["label"].lower(), p["key"].lower()):
                i = scope.find(needle)
                if i != -1 and i < best_pos:
                    best, best_pos = p, i
        if best:
            return best["key"], best["label"]
    return None, None


def classify_antenna(pdf_bytes: bytes, router_prompt: str, profiles: list,
                     model: str = DEFAULT_CLASSIFY_MODEL, api_key: str | None = None) -> dict:
    """Return {key, label, reason, cost}. `profiles` is [{key, label}, ...]."""
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ExtractionError("ANTHROPIC_API_KEY is not set in the environment.")
    if not profiles:
        raise ExtractionError("This workflow declares no antenna-type profiles.")

    client = anthropic.Anthropic(api_key=api_key)
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
    resp = client.messages.create(
        model=model,
        max_tokens=_CLASSIFY_MAX_TOKENS,
        messages=[{
            "role": "user",
            "content": [
                {"type": "document",
                 "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}},
                {"type": "text", "text": router_prompt},
            ],
        }],
    )
    cost = usage_cost(getattr(resp, "usage", None), model)
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    key, label = _match_profile(text, profiles)
    return {"key": key, "label": label, "reason": text, "cost": cost}
