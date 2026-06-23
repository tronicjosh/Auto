"""Config-driven engine: generic row mapping + validation, composed from named blocks.

A workflow declares, in its config:
  * mapping_spec — for each output column, where its value comes from (a section field, a
    root field, an override, or a constant) and an optional named transform; and which list
    field is expanded one-row-per-item (`row_source`).
  * rules_spec  — a list of validation rules: declarative ones (in_vocab, equals_count,
    only_when) and named checks (tilt_range, gain_plausibility, ports_unique_per_group).

The transforms/checks are a shared registry — the engine's reusable building blocks. New
logic is added here once (named) and referenced from any workflow's config by name. No
per-workflow Python is needed for the common case.
"""

import math

from .util import normalize_ports, normalize_tilt, parse_ports, parse_tilt_range, to_cell_str, to_float

# --------------------------------------------------------------------------- #
# Mapping: named value transforms.  signature: fn(raw, ctx, params) -> str
# --------------------------------------------------------------------------- #

def _t_normalize_tilt(raw, ctx, p):
    return normalize_tilt(to_cell_str(raw))


def _t_normalize_ports(raw, ctx, p):
    return normalize_ports(to_cell_str(raw))


def _t_count_ports(raw, ctx, p):
    return str(len(parse_ports(normalize_ports(to_cell_str(raw)))))


def _t_blank_unless(raw, ctx, p):
    """Keep the value only when another field on the same item equals a given value."""
    other = to_cell_str(ctx["item"].get(p["field"])).strip().lower()
    return to_cell_str(raw) if other == str(p.get("equals", "")).strip().lower() else ""


TRANSFORMS = {
    "normalize_tilt": _t_normalize_tilt,
    "normalize_ports": _t_normalize_ports,
    "count_ports": _t_count_ports,
    "blank_unless": _t_blank_unless,
}


def _resolve(rule, data, item, overrides, ctx):
    if "const" in rule:
        return rule["const"]
    if "from" in rule:                      # an injected value (manufacturer/model/source override)
        raw = overrides.get(rule["from"], "")
    elif "root" in rule:                    # a top-level field, optionally overridden
        ov = rule.get("override")
        ov_val = overrides.get(ov, "") if ov else ""
        raw = ov_val if str(ov_val).strip() else data.get(rule["root"])
    elif "field" in rule:                   # a field on the expanded list item
        raw = item.get(rule["field"])
    else:
        raw = ""
    t = rule.get("transform")
    if not t:
        return to_cell_str(raw)
    name, params = (t, {}) if isinstance(t, str) else (t["name"], t)
    return TRANSFORMS[name](raw, ctx, params)


def generic_map_rows(data, spec, manufacturer="", model_name="", source=""):
    """Expand the model's JSON into one row dict per item, per the mapping_spec."""
    overrides = {"manufacturer": manufacturer, "model_name": model_name, "source": source}
    colrules = spec["columns"]
    src = spec.get("row_source")
    items = (data.get(src) or []) if src else [{}]
    rows = []
    for item in items:
        ctx = {"item": item, "data": data}
        rows.append({col: _resolve(rule, data, item, overrides, ctx)
                     for col, rule in colrules.items()})
    return rows


# --------------------------------------------------------------------------- #
# Validation: declarative rules + named checks.
# --------------------------------------------------------------------------- #

def _check_tilt_range(rows, vocab, flags, p):
    col = p.get("column", "Tilts [0,1,2,3]")
    for i, row in enumerate(rows):
        raw = row.get(col, "").strip()
        if not raw:
            continue
        if "," in raw:  # discrete tilt options, e.g. "2,6,10" — validate each value
            vals = [to_float(v) for v in raw.split(",")]
            if any(v is None for v in vals):
                flags[i][col] = "Unparseable tilt value"
            elif any(v < 0 for v in vals):
                flags[i][col] = "Tilt must be >= 0"
            continue
        rng = parse_tilt_range(raw)
        if rng is None:
            flags[i][col] = "Unparseable tilt value"
        elif rng[0] < 0 or rng[1] < 0:
            flags[i][col] = "Tilt must be >= 0"
        elif rng[0] > rng[1]:
            flags[i][col] = "Low tilt exceeds high tilt"


def _check_gain_plausibility(rows, vocab, flags, p):
    for i, row in enumerate(rows):
        hbw = to_float(row.get("Horizontal HPBW [deg]", ""))
        vbw = to_float(row.get("Vertical HPBW [deg]", ""))
        gain = to_float(row.get("Gain [dBi]", ""))
        if hbw and vbw and gain is not None and hbw > 0 and vbw > 0:
            diff = 10 * math.log10(41253.0 / (hbw * vbw)) - gain
            if not (-1.0 <= diff <= 6.0):
                flags[i]["Gain [dBi]"] = (
                    f"Implausible gain (directivity-gain delta {diff:.1f} dB outside -1..+6)")


def _check_ports_unique_per_group(rows, vocab, flags, p):
    group_col, ports_col = p.get("group", "Frequency"), p.get("ports", "Section Ports")
    groups = {}
    for i, row in enumerate(rows):
        key = row.get(group_col, "").strip()
        if key:
            groups.setdefault(key, []).append((i, parse_ports(row.get(ports_col, ""))))
    for entries in groups.values():
        seen, clashing = {}, set()
        for ri, ports in entries:
            for port in ports:
                if port in seen and seen[port] != ri:
                    clashing.add(ri)
                    clashing.add(seen[port])
                else:
                    seen.setdefault(port, ri)
        for ri in clashing:
            existing = flags[ri].get(ports_col)
            msg = "Port shared with another section of the same Frequency"
            flags[ri][ports_col] = f"{existing}; {msg}" if existing else msg


CHECKS = {
    "tilt_range": _check_tilt_range,
    "gain_plausibility": _check_gain_plausibility,
    "ports_unique_per_group": _check_ports_unique_per_group,
}


def _rule_in_vocab(rows, vocab, flags, rule):
    col = rule["column"]
    allowed = set(vocab.get(rule["vocab"], []))
    msg = rule.get("message", f"Not in {col} vocabulary")
    for i, row in enumerate(rows):
        val = row.get(col, "").strip()
        if val and val not in allowed:
            flags[i][col] = msg


def _rule_equals_count(rows, vocab, flags, rule):
    col, counts = rule["column"], rule["counts"]
    for i, row in enumerate(rows):
        n = len(parse_ports(row.get(counts, "")))
        if row.get(col, "").strip() != str(n):
            flags[i][col] = f"Expected {n} (count of {counts})"


def _rule_only_when(rows, vocab, flags, rule):
    when_col, when_val = rule["when_column"], rule["when_equals"]
    for i, row in enumerate(rows):
        if row.get(when_col, "").strip() != when_val:
            for col in rule["columns"]:
                if row.get(col, "").strip():
                    flags[i][col] = f"Only used when {when_col} = {when_val}"


_RULES = {"in_vocab": _rule_in_vocab, "equals_count": _rule_equals_count, "only_when": _rule_only_when}


def generic_validate(rows, vocab, spec):
    """Apply a rules_spec to rows; return one flag dict per row ({} = clean)."""
    flags = [dict() for _ in rows]
    for rule in spec:
        t = rule["type"]
        if t == "check":
            CHECKS[rule["name"]](rows, vocab, flags, rule)
        else:
            _RULES[t](rows, vocab, flags, rule)
    return flags


def select_overlapping_band_gains(rows, data, bands, spec):
    """Deterministically set each standard-band row's Gain/HPBW/VPBW from the OVERLAPPING
    datasheet column with the HIGHEST gain.

    The model transcribes the raw datasheet frequency columns (range in MHz + gain + beamwidths)
    into `data[source_field]`; this code does the overlap + max-gain selection that the model is
    unreliable at. Rows whose IXUS band has no overlapping column — and "Custom" rows — keep the
    model's own values, so a missing/blank transcription degrades gracefully.
    """
    raw = data.get(spec.get("source_field", "datasheet_bands")) or []
    scale = 1_000_000 if spec.get("unit", "mhz") == "mhz" else 1
    cols = []
    for b in raw:
        lo, hi, g = to_float(b.get("min_mhz")), to_float(b.get("max_mhz")), to_float(b.get("gain_dbi"))
        if lo is None or hi is None or g is None:
            continue
        if lo > hi:
            lo, hi = hi, lo
        cols.append((lo * scale, hi * scale, g, b.get("hbw_deg"), b.get("vbw_deg")))
    if not cols:
        return rows

    band_minmax = {b["name"]: (b.get("min_hz"), b.get("max_hz")) for b in bands}
    fc = spec.get("freq_column", "Frequency")
    gc, hc, vc = spec.get("gain_column"), spec.get("hbw_column"), spec.get("vbw_column")
    for row in rows:
        rng = band_minmax.get(row.get(fc, "").strip())
        if not rng or rng[0] is None or rng[1] is None:
            continue  # Custom or unknown band -> leave the model's values
        blo, bhi = rng
        overlapping = [c for c in cols if c[1] >= blo and c[0] <= bhi]
        if not overlapping:
            continue
        best = max(overlapping, key=lambda c: c[2])  # highest gain
        row[gc] = to_cell_str(best[2])
        row[hc] = to_cell_str(best[3])
        row[vc] = to_cell_str(best[4])
    return rows


def apply_type_guardrails(rows, flags, guardrails):
    """Flag rows that break the confirmed antenna-type's invariants (mutates + returns flags).

    `guardrails` is the list for one profile (e.g. parabolic). Each entry is one of:
      {"column": C, "equals": V}   value must equal V (numeric-aware: "0" == "0.0")
      {"column": C, "required": true}  value must be present
      {"column": C, "blank": true}     value must be blank
      {"columns_equal": [A, B]}        the two columns must match
    """
    for i, row in enumerate(rows):
        for g in guardrails:
            msg = g.get("message")
            if "columns_equal" in g:
                cols = g["columns_equal"]
                vals = [row.get(c, "").strip() for c in cols]
                nums = [to_float(v) for v in vals]
                differ = (len({round(n, 6) for n in nums}) > 1
                          if all(n is not None for n in nums) else len(set(vals)) > 1)
                if differ:
                    for c in cols:
                        flags[i].setdefault(c, msg or "values should be equal")
                continue
            col = g.get("column")
            if not col:
                continue
            val = row.get(col, "").strip()
            if g.get("required") and not val:
                flags[i].setdefault(col, msg or f"{col} is required for this type")
            elif g.get("blank") and val:
                flags[i].setdefault(col, msg or f"{col} should be blank for this type")
            elif "equals" in g:
                want = str(g["equals"]).strip()
                nv, nw = to_float(val), to_float(want)
                same = (nv == nw) if (nv is not None and nw is not None) else (val == want)
                if not same:
                    flags[i].setdefault(col, msg or f"{col} should be {want} for this type")
    return flags
