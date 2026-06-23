"""A live Claude conversation about one datasheet.

The first turn sends the PDF + extraction prompt. Subsequent `refine` turns append
the user's feedback and ask for the full corrected JSON again, so the model keeps the
datasheet in context across the back-and-forth. The PDF block is marked for prompt
caching so re-sending the history on each refine stays cheap.
"""

import base64
import os

import anthropic

from .config import DEFAULT_MODEL, MAX_TOKENS
from .extract import ExtractionError, parse_model_json
from .pricing import usage_cost
from .prompt import build_extraction_prompt

_REFINE_INSTRUCTION = (
    "The user reviewed the result and asks for these changes:\n\n{feedback}\n\n"
    "Apply them and return the COMPLETE corrected JSON object (the same schema as before "
    "— all sections, not just the changed ones). Before the JSON, write ONE short sentence "
    "describing what you changed."
)


class Conversation:
    """Holds the Anthropic message history for one datasheet session."""

    def __init__(self, pdf_bytes: bytes, vocab: dict, manufacturer: str = "",
                 model_name: str = "", model: str = DEFAULT_MODEL, api_key: str | None = None,
                 build_prompt=None):
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ExtractionError("ANTHROPIC_API_KEY is not set in the environment.")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.vocab = vocab
        self.manufacturer = manufacturer
        self.model_name = model_name
        self.calls: list[dict] = []  # per-API-call token + cost breakdown

        pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
        # A workflow can supply its own prompt builder; default to the antenna prompt.
        builder = build_prompt or (lambda v: build_extraction_prompt(
            v.get("frequency", []), v.get("type", [])))
        prompt = builder(vocab)
        self.messages = [{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64},
                    "cache_control": {"type": "ephemeral"},  # cache the PDF across refine turns
                },
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

    @property
    def last_call(self) -> dict | None:
        """Token + cost breakdown for the most recent API call."""
        return self.calls[-1] if self.calls else None

    def total_cost(self) -> float:
        """Running USD total across every API call in this session."""
        return round(sum(c["cost_usd"] for c in self.calls), 6)

    def cost_summary(self) -> dict:
        """What this session has cost so far — per-call list + running total."""
        return {"calls": self.calls, "total_usd": self.total_cost(),
                "n_calls": len(self.calls), "model": self.model}

    def extract(self) -> dict:
        """Run the initial extraction turn; returns the parsed JSON dict."""
        return parse_model_json(self._call())

    def refine(self, feedback: str):
        """Apply a user instruction; returns (data, note) where note is a one-line summary."""
        self.messages.append({
            "role": "user",
            "content": _REFINE_INSTRUCTION.format(feedback=feedback),
        })
        text = self._call()
        data = parse_model_json(text)
        brace = text.find("{")
        note = (text[:brace].strip() if brace > 0 else "").strip()
        return data, note

    def discard_last_turn(self) -> None:
        """Drop the most recent refine (user instruction + assistant reply) so the model's
        context matches the screen after a revert. A refine always adds exactly 2 messages."""
        if len(self.messages) >= 3:  # keep at least the initial user turn
            del self.messages[-2:]
