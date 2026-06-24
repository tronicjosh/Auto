import re

from antenna_reader import schema
from antenna_reader.workflows import get_workflow


def test_model_slash_is_reformatted_to_dash():
    # '/' breaks the downstream file-path program, so the live workflow stores it as '-'.
    wf = get_workflow("antenna")
    data = {"manufacturer": "Kathrein", "model": "KRE 101 2524/1MU", "type": "panel",
            "sections": [{"frequency": "750 MHz", "ports": "1"}]}
    rows, _ = wf.build_rows(data, {"source": ["EMSS"], "frequency": ["750 MHz"], "type": ["panel"]})
    assert rows[0]["Model"] == "KRE 101 2524-1MU"


def test_decimal_comma_becomes_dot_in_numeric_cells_only():
    # European-style decimals ("12,5") are normalised to "12.5"; list commas are untouched.
    wf = get_workflow("antenna")
    data = {"manufacturer": "M", "model": "X", "type": "panel",
            "sections": [{"frequency": "Custom", "minFreqHz": "1", "maxFreqHz": "2",
                          "gain_dbi": "12,5", "hbw_deg": "7,3", "vbw_deg": "8",
                          "ports": "1,2", "tilts": "2,6", "azimuth": "0"}]}
    rows, _ = wf.build_rows(data, {"source": ["EMSS"], "frequency": ["Custom"], "type": ["panel"]})
    assert rows[0]["Gain [dBi]"] == "12.5"
    assert rows[0]["Horizontal HPBW [deg]"] == "7.3"
    assert rows[0]["Section Ports"] == "1,2"        # list comma preserved
    assert rows[0]["Tilts [0,1,2,3]"] == "2,6"      # discrete-tilt list comma preserved


def test_antenna_workflow_loads_from_config_files():
    wf = get_workflow("antenna")
    assert wf is not None and wf.enabled
    # The output contract in meta.json must match the engine's column contract.
    assert wf.columns == schema.COLUMNS
    assert wf.numeric_columns == schema.NUMERIC_COLUMNS
    assert wf.extras["rules"]
    # Generic config-section mechanism: a 'bands' table is declared and has data.
    specs = {s["key"]: s for s in wf.extras["sections"]}
    assert "bands" in specs and specs["bands"]["inject_tag"] == "[[BANDS]]"
    assert wf.extras["section_data"].get("bands")
    assert wf.ui.get("header_title")
    assert wf.extras["config_dir"].replace("\\", "/") == "workflow_configs/antenna"


def test_prompt_built_from_file_injects_vocab_and_sections():
    wf = get_workflow("antenna")
    p = wf.build_prompt({"frequency": ["750 MHz", "Custom"], "type": ["panel"],
                         "manufacturers": ["CommScope", "Kathrein"]})
    assert "750 MHz" in p and "panel" in p          # frequency/type vocab injected
    assert "CommScope" in p and "Kathrein" in p     # GENERIC injection: any vocab key works
    assert re.search(r"- .+: \d+ to \d+ Hz", p)     # a band row rendered from the bands table
    assert "Respond ONLY with JSON" in p            # prompt.txt body present
    assert "[[" not in p                            # every tag substituted/cleared


def test_build_prompt_is_profile_aware():
    wf = get_workflow("antenna")
    v = {"frequency": ["750 MHz"], "type": ["panel", "parabolic reflector"],
         "manufacturers": ["CommScope"]}
    p = wf.build_prompt(v, "parabolic")
    assert "Parabolic reflector" in p and "boresight" in p       # parabolic profile spliced in
    assert "rectangular radome" not in p                         # panel rules NOT present
    assert "Respond ONLY with JSON" in p
    assert "[[" not in p


def test_workflow_exposes_router_profiles_and_guardrails():
    wf = get_workflow("antenna")
    assert [p["key"] for p in wf.extras["profiles"]] == ["panel", "omni", "lens", "parabolic"]
    assert wf.extras["router_prompt"]
    assert wf.extras["classify_model"] == "claude-haiku-4-5"
    assert "parabolic" in wf.extras["type_guardrails"]


def test_source_defaults_from_vocab_not_hardcoded():
    wf = get_workflow("antenna")
    data = {"manufacturer": "CommScope", "model": "M", "type": "panel",
            "sections": [{"frequency": "750 MHz", "ports": "1", "tilts": "2"}]}
    # No source supplied -> defaults to the first workbook source-vocab value (config, not code).
    rows, _ = wf.build_rows(data, {"source": ["EMSS", "NAD"], "frequency": [], "type": []})
    assert rows[0]["Antenna Source"] == "EMSS"
    # A user-selected source overrides the default.
    rows, _ = wf.build_rows(data, {"source": ["EMSS", "NAD"], "frequency": [], "type": []},
                            source="NAD")
    assert rows[0]["Antenna Source"] == "NAD"


def test_vocab_injection_is_generic_for_arbitrary_keys():
    # A brand-new workflow could declare ANY vocab column; build_prompt must inject it by tag
    # without the engine knowing the key in advance.
    wf = get_workflow("antenna")
    p = wf.build_prompt({"source": ["EMSS", "NAD"]})
    # the antenna prompt has no [[SOURCE_VOCAB]] tag, but the mechanism still resolves cleanly
    assert "[[" not in p
