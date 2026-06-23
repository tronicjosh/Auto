"""Build a Workflow from external config files — so a workflow's definition (its text,
prompt, columns, and structured edge-case tables) lives in `workflow_configs/<id>/`,
not in code.

A config folder contains:
    meta.json     identity, on-screen text (ui), columns, rules, and `config_sections`
    prompt.txt    the AI instruction note, with tags filled in at call time:
                  one [[<KEY>_VOCAB]] tag per controlled vocabulary the reader returns
                  (e.g. [[FREQUENCY_VOCAB]], [[TYPE_VOCAB]], [[MANUFACTURERS_VOCAB]]) and
                  one tag per declared config section (e.g. [[BANDS]])
    <key>.json    the rows for each declared config section (e.g. bands.json)

`config_sections` is what makes the structured config GENERIC: each entry declares a
table (its columns, how each row is written into the prompt, and the tag to inject it at).
A brand-new workflow declares whatever tables it needs — no antenna assumptions.

Only the engine hooks (JSON->rows, validation, workbook writing) come from code.
"""

import json
import re
from pathlib import Path

from ..config import DEFAULT_CLASSIFY_MODEL, DEFAULT_MODEL, PROJECT_ROOT
from ..engine import generic_map_rows, generic_validate, select_overlapping_band_gains
from ..vocab import read_vocabularies
from ..workbook import write_populated
from .base import Workflow

CONFIG_ROOT = PROJECT_ROOT / "workflow_configs"
TEMPLATE_DIR = PROJECT_ROOT / "data" / "template"

_TAG_RE = re.compile(r"\[\[[A-Z0-9_]+\]\]")  # leftover tags get cleared so none reach the model


def _render_section(spec: dict, rows: list) -> str:
    """Turn a config section's rows into the text injected at its tag."""
    if not rows:
        return ""
    cols = [c["key"] for c in spec.get("columns", [])]
    row_tmpl = spec.get("row_template") or ("- " + " | ".join("{" + c + "}" for c in cols))
    lines = []
    for r in rows:
        safe = {c: r.get(c, "") for c in cols}
        safe.update({k: v for k, v in r.items() if isinstance(k, str)})
        try:
            lines.append(row_tmpl.format(**safe))
        except Exception:
            lines.append(row_tmpl)
    intro = spec.get("intro", "")
    return (intro + "\n" if intro else "") + "\n".join(lines)


def _build_read_vocab(meta, fallback):
    """Prefer a config-declared vocab_spec (sheet + column->key map); else the passed hook."""
    spec = meta.get("vocab_spec")
    if spec:
        cols, sheet = spec.get("columns", {}), spec.get("sheet")
        return lambda t, _c=cols, _s=sheet: read_vocabularies(t, column_map=_c, sheet=_s)
    return fallback or read_vocabularies


def _build_map_rows(meta, fallback):
    """Prefer a config-declared mapping_spec; else the passed hook."""
    spec = meta.get("mapping_spec")
    if spec:
        return lambda data, m="", mn="", s="", _sp=spec: generic_map_rows(data, _sp, m, mn, s)
    return fallback


def _build_validate(meta, fallback):
    """Prefer a config-declared rules_spec; else the passed hook."""
    spec = meta.get("rules_spec")
    if spec is not None:
        return lambda rows, vocab, _sp=spec: generic_validate(rows, vocab, _sp)
    return fallback


def _build_write_output(meta, columns, numeric_columns, fallback):
    """Build the xlsx writer from config (columns + sheet + output_spec); else the passed hook."""
    sheet = meta.get("output_sheet_name")
    ospec = meta.get("output_spec")
    if sheet or ospec:
        return (lambda t, rows, out, _c=columns, _n=numeric_columns, _s=sheet, _o=ospec:
                write_populated(t, rows, out, columns=_c, numeric_columns=_n,
                                sheet_name=_s, output_spec=_o))
    return fallback or write_populated


def load_workflow(config_dir, *, read_vocab=None, sections_to_rows=None, validate_rows=None,
                  write_output=None) -> Workflow:
    """Read a config folder and assemble a Workflow.

    Engine behaviour is built from config *specs* (vocab_spec / mapping_spec / rules_spec) so
    a new workflow needs no code; the explicit hook args remain as a fallback during migration.
    """
    config_dir = Path(config_dir)
    meta = json.loads((config_dir / "meta.json").read_text(encoding="utf-8"))

    # The extraction prompt: a base template (universal rules + the [[PROFILE]] slot) plus one
    # short per-type profile spliced in. Falls back to the legacy single prompt.txt.
    base_file = config_dir / meta.get("prompt_base", "prompt.txt")
    if not base_file.exists():
        base_file = config_dir / "prompt.txt"
    prompt_template = base_file.read_text(encoding="utf-8")

    profiles_meta = meta.get("profiles", [])
    profile_labels = {p["key"]: p.get("label", p["key"]) for p in profiles_meta}
    profile_texts = {}
    for p in profiles_meta:
        pf = config_dir / "profiles" / f"{p['key']}.txt"
        profile_texts[p["key"]] = pf.read_text(encoding="utf-8") if pf.exists() else ""

    router_file = config_dir / meta.get("router_prompt", "")
    router_prompt = router_file.read_text(encoding="utf-8") if router_file.is_file() else ""

    columns = list(meta["columns"])
    numeric_columns = frozenset(meta["numeric_columns"])
    read_vocab = _build_read_vocab(meta, read_vocab)
    sections_to_rows = _build_map_rows(meta, sections_to_rows)
    validate_rows = _build_validate(meta, validate_rows)
    write_output = _build_write_output(meta, columns, numeric_columns, write_output)

    section_specs = meta.get("config_sections", [])
    section_data = {}
    for spec in section_specs:
        key = spec.get("key")
        if not key:
            continue
        f = config_dir / f"{key}.json"
        section_data[key] = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []

    # Optional deterministic band-gain selection from the model's raw datasheet-column transcription.
    adjust_rows = None
    gspec = meta.get("band_gain_spec")
    if gspec:
        gbands = section_data.get(gspec.get("bands_section", "bands"), [])
        adjust_rows = (lambda rows, data, _b=gbands, _s=gspec:
                       select_overlapping_band_gains(rows, data, _b, _s))

    def build_prompt(vocab, profile_key=None, _tmpl=prompt_template, _specs=section_specs,
                     _data=section_data, _ptext=profile_texts, _plabel=profile_labels):
        # Splice in the per-type profile (its rules + display name) before the vocab.
        text = _tmpl.replace("[[PROFILE_NAME]]", _plabel.get(profile_key, "") or "")
        text = text.replace("[[PROFILE]]", _ptext.get(profile_key, "") or "")
        # Inject EVERY controlled vocabulary the workflow's reader returns, generically:
        # a vocab key fills the tag [[<KEY>_VOCAB]] — e.g. "frequency" -> [[FREQUENCY_VOCAB]],
        # "manufacturers" -> [[MANUFACTURERS_VOCAB]], "source" -> [[SOURCE_VOCAB]]. No tag
        # names are hard-coded here, so a new workflow's vocab columns are usable immediately.
        for key, values in vocab.items():
            if isinstance(values, (list, tuple)):
                text = text.replace(f"[[{key.upper()}_VOCAB]]",
                                    ", ".join(str(v) for v in values))
        for spec in _specs:
            tag = spec.get("inject_tag")
            if tag:
                text = text.replace(tag, _render_section(spec, _data.get(spec["key"], [])))
        return _TAG_RE.sub("", text)  # clear any tag with no data/section

    return Workflow(
        id=meta["id"],
        title=meta["title"],
        description=meta["description"],
        model=meta.get("model", DEFAULT_MODEL),
        template_path=TEMPLATE_DIR / meta["template"],
        output_sheet_name=meta["output_sheet_name"],
        columns=columns,
        numeric_columns=numeric_columns,
        diff_key_columns=list(meta["diff_key_columns"]),
        read_vocab=read_vocab,
        build_prompt=build_prompt,
        sections_to_rows=sections_to_rows,
        validate_rows=validate_rows,
        write_output=write_output,
        adjust_rows=adjust_rows,
        enabled=meta.get("enabled", True),
        ui=meta.get("ui", {}),
        extras={
            "sections": section_specs,
            "section_data": section_data,
            "rules": meta.get("rules", []),
            "config_dir": config_dir.relative_to(PROJECT_ROOT).as_posix(),
            "profiles": [{"key": p["key"], "label": profile_labels[p["key"]]} for p in profiles_meta],
            "router_prompt": router_prompt,
            "classify_model": meta.get("classify_model", DEFAULT_CLASSIFY_MODEL),
            "type_guardrails": meta.get("type_guardrails", {}),
            "base_prompt": prompt_template,
            "prompt_base_file": base_file.name,
        },
    )
