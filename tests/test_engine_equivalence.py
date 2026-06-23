"""The config-driven engine must reproduce the proven antenna functions exactly.

These oracle tests pin the generic mapping/validation (used by the live workflow) to the
original rows.py / validate.py (still tested directly), so 'config + engine' can never
silently drift from the verified behaviour.
"""

import json

from antenna_reader.config import PROJECT_ROOT
from antenna_reader.engine import generic_map_rows, generic_validate
from antenna_reader.rows import sections_to_rows
from antenna_reader.schema import COLUMNS
from antenna_reader.validate import validate_rows
from antenna_reader.workflows import get_workflow

_META = json.loads((PROJECT_ROOT / "workflow_configs" / "antenna" / "meta.json")
                   .read_text(encoding="utf-8"))
MAPPING_SPEC = _META["mapping_spec"]
RULES_SPEC = _META["rules_spec"]

VOCAB = {
    "frequency": ["Custom", "750 MHz", "850 MHz band", "1800 MHz band",
                  "1.95 GHz", "2100 MHz band", "2.35 GHz"],
    "type": ["panel", "omni"],
}


def _blank(**kw):
    row = {c: "" for c in COLUMNS}
    row.update(kw)
    return row


def test_mapping_matches_rows_module_on_golden(commscope_json):
    want = sections_to_rows(commscope_json, source="EMSS")
    got = generic_map_rows(commscope_json, MAPPING_SPEC, source="EMSS")
    assert got == want


def test_mapping_honours_overrides_like_rows_module(commscope_json):
    want = sections_to_rows(commscope_json, manufacturer="Acme", model_name="X1", source="NAD")
    got = generic_map_rows(commscope_json, MAPPING_SPEC, manufacturer="Acme",
                           model_name="X1", source="NAD")
    assert got == want


def test_validation_matches_validate_module():
    cases = [
        _blank(Frequency="750 MHz", Type="panel",
               **{"Section Ports": "1,2,5,6", "Number of Ports": "4",
                  "Tilts [0,1,2,3]": "2 to 20", "Gain [dBi]": "13.7",
                  "Horizontal HPBW [deg]": "42", "Vertical HPBW [deg]": "23.7"}),
        _blank(Frequency="700 MHz", Type="panl"),
        _blank(**{"Section Ports": "1,2,3", "Number of Ports": "4"}),
        _blank(Frequency="750 MHz", **{"Min Freq [Hz]": "700000000"}),
        _blank(**{"Tilts [0,1,2,3]": "20 to 2"}),
        _blank(**{"Gain [dBi]": "2", "Horizontal HPBW [deg]": "33", "Vertical HPBW [deg]": "7.3"}),
    ]
    assert generic_validate(cases, VOCAB, RULES_SPEC) == validate_rows(cases, VOCAB)


def test_duplicate_ports_match():
    rows = [_blank(Frequency="750 MHz", **{"Section Ports": "1,2", "Number of Ports": "2"}),
            _blank(Frequency="750 MHz", **{"Section Ports": "2,3", "Number of Ports": "2"})]
    assert generic_validate(rows, VOCAB, RULES_SPEC) == validate_rows(rows, VOCAB)


def test_live_workflow_build_rows_reproduces_golden(commscope_json, golden_rows):
    """The actual workflow (now fully config-driven) must still produce the golden sheet."""
    wf = get_workflow("antenna")
    rows, _ = wf.build_rows(commscope_json, {"source": ["EMSS", "NAD"], **VOCAB},
                            source="EMSS")
    assert rows == golden_rows


def test_config_driven_writer_matches_default(golden_rows):
    """The workflow's config-built xlsx writer must be byte-identical to the default writer."""
    import io

    from antenna_reader.config import TEMPLATE_PATH
    from antenna_reader.workbook import write_populated

    wf = get_workflow("antenna")
    via_config = io.BytesIO()
    wf.write_output(wf.template_path, golden_rows, via_config)
    via_default = io.BytesIO()
    write_populated(TEMPLATE_PATH, golden_rows, via_default)
    assert via_config.getvalue() == via_default.getvalue()
