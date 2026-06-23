"""Call the Claude API: PDF (base64 document block) -> strict-JSON extraction dict."""

import base64
import datetime
import json
import os
import re
import sys

import anthropic

from .config import DEFAULT_MODEL, MAX_TOKENS, PROJECT_ROOT
from .prompt import build_extraction_prompt


class ExtractionError(RuntimeError):
    """Raised when extraction cannot proceed or the model output is unusable."""


def extract_from_pdf(pdf_bytes: bytes, vocab: dict, model: str = DEFAULT_MODEL,
                     api_key: str | None = None) -> dict:
    """Send the PDF to Claude and return the parsed extraction JSON."""
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ExtractionError("ANTHROPIC_API_KEY is not set in the environment.")

    client = anthropic.Anthropic(api_key=api_key)
    prompt = build_extraction_prompt(vocab.get("frequency", []), vocab.get("type", []))
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    response = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": pdf_b64,
                    },
                },
                {"type": "text", "text": prompt},
            ],
        }],
    )

    text = "".join(b.text for b in response.content if b.type == "text").strip()
    return parse_model_json(text)


_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)


def _scan_balanced_json(text: str):
    """Find the first balanced {...} that parses as JSON, ignoring braces inside strings.

    Robust against a prose preamble (even one containing stray braces) and missing/extra
    code fences, because it brace-counts with string-awareness and tries each '{' start.
    """
    for start in (i for i, ch in enumerate(text) if ch == "{"):
        depth = 0
        in_str = False
        esc = False
        for j in range(start, len(text)):
            ch = text[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:j + 1])
                    except json.JSONDecodeError:
                        break  # not valid from this start; try the next '{'
    return None


def _log_parse_failure(text: str) -> None:
    """Persist the unparseable reply so the failure can be diagnosed (not guessed)."""
    try:
        d = PROJECT_ROOT / "conversations" / "_parse_failures"
        d.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S_%f")
        (d / f"{stamp}.txt").write_text(text, encoding="utf-8")
    except Exception:
        pass
    print(f"[parse_model_json] FAILED to parse model reply (len={len(text)}). "
          f"head={text[:120]!r} tail={text[-120:]!r}", file=sys.stderr, flush=True)


def parse_model_json(text: str) -> dict:
    """Pull the JSON object out of the model reply, tolerating a prose preamble and
    markdown code fences (the model often 'thinks out loud' before the JSON)."""
    text = text.strip()
    # 1. Prefer a fenced ```json {...} ``` block — unambiguous even amid prose.
    m = _FENCE_RE.search(text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # 2. The whole reply is the JSON object.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 3. First balanced, string-aware {...} that parses.
    obj = _scan_balanced_json(text)
    if obj is not None:
        return obj
    _log_parse_failure(text)
    raise ExtractionError("Model did not return valid JSON.")
