"""Small shared parsing helpers used by row-building and validation."""

import re

_UNSIGNED_NUM = re.compile(r"\d+(?:\.\d+)?")


def to_cell_str(value) -> str:
    """Render a JSON scalar as a clean cell string ('' for None/blank).

    Whole-number floats lose the trailing '.0' (27.0 -> '27') so port counts and
    azimuths read naturally.
    """
    if value is None:
        return ""
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return repr(value)
    return str(value).strip()


def parse_ports(text) -> list[str]:
    """'1,2,5,6' -> ['1','2','5','6'] (ignores blanks/whitespace)."""
    return [p.strip() for p in str(text).split(",") if p.strip()]


def to_float(text):
    """Best-effort float parse; returns None if not a number."""
    try:
        return float(str(text).strip())
    except (ValueError, AttributeError):
        return None


def parse_tilt_range(text):
    """'2 to 20' -> (2.0, 20.0); '5' -> (5.0, 5.0); unparseable -> None."""
    t = str(text).strip().lower()
    if not t:
        return None
    if "to" in t:
        parts = t.split("to")
        lo, hi = to_float(parts[0]), to_float(parts[1])
        if lo is None or hi is None:
            return None
        return lo, hi
    v = to_float(t)
    if v is None:
        return None
    return v, v


def _fmt_num_token(token: str) -> str:
    f = float(token)
    return str(int(f)) if f.is_integer() else repr(f)


def normalize_tilt(text) -> str:
    """Canonicalise a tilt to 'low to high' (e.g. '2-20' or '2 deg to 20 deg' -> '2 to 20')
    or a single number. Tilts are non-negative downtilts, so a hyphen between two values
    is a range separator, not a minus sign. Unrecognised shapes are returned unchanged.
    """
    t = str(text).strip()
    if not t:
        return ""
    nums = _UNSIGNED_NUM.findall(t)
    # A comma means DISCRETE tilt options (e.g. "2,6,10" for "2° or 6° or 10°"), NOT a range —
    # keep them comma-separated. This also fixes the 2-value case ("2,10" must not become a range).
    if "," in t:
        return ",".join(_fmt_num_token(n) for n in nums) if nums else t
    if len(nums) == 2:
        return f"{_fmt_num_token(nums[0])} to {_fmt_num_token(nums[1])}"
    if len(nums) == 1:
        return _fmt_num_token(nums[0])
    return t


def normalize_ports(text) -> str:
    """Re-join a port list with single commas, accepting spaces / slashes / semicolons
    as separators: '1, 2 / 5;6' -> '1,2,5,6'. Tokens are kept verbatim (e.g. 'R1')."""
    tokens = [tok for tok in re.split(r"[\s,;/]+", str(text).strip()) if tok]
    return ",".join(tokens)
