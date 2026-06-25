"""Wraps one Claude extraction call for a datasheet: send the PDF + prompt, parse the JSON.

A small class (rather than a bare function) so it owns the message and the per-call token/cost
breakdown shown in the GUI.
"""

import base64
import os

import anthropic

from .config import DEFAULT_MODEL, MAX_TOKENS
from .extract import ExtractionError, parse_model_json
from .pricing import usage_cost


class Conversation:
    """Wraps the single PDF -> JSON extraction call for one datasheet."""

    def __init__(self, pdf_bytes: bytes, vocab: dict, build_prompt, *,
                 model: str = DEFAULT_MODEL, api_key: str | None = None):
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ExtractionError("ANTHROPIC_API_KEY is not set in the environment.")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.calls: list[dict] = []  # per-API-call token + cost breakdown

        pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
        prompt = build_prompt(vocab)  # config-driven: base_prompt + the chosen profile + vocab
        self.messages = [{
            "role": "user",
            "content": [
                {"type": "document",
                 "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}},
                {"type": "text", "text": prompt},
            ],
        }]

    def _call(self) -> str:
        resp = self.client.messages.create(
            model=self.model, max_tokens=MAX_TOKENS, messages=self.messages,
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        self.messages.append({"role": "assistant", "content": text})
        self.calls.append(usage_cost(getattr(resp, "usage", None), self.model))
        return text

    def extract(self) -> dict:
        """Run the extraction call; returns the parsed JSON dict."""
        return parse_model_json(self._call())
