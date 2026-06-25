"""Robustly pull the strict-JSON extraction object out of a model reply, and define
ExtractionError — the shared error type for the AI layer."""

import json
import re
import sys


class ExtractionError(RuntimeError):
    """Raised when extraction cannot proceed or the model output is unusable."""


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
    """Report the unparseable reply to stderr so the failure can be diagnosed."""
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
