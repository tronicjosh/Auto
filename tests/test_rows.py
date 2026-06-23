from antenna_reader.rows import sections_to_rows
from antenna_reader.schema import COLUMNS
from antenna_reader.util import (
    normalize_ports,
    normalize_tilt,
    parse_ports,
    parse_tilt_range,
    to_cell_str,
)


def test_commscope_expands_to_golden(commscope_json, golden_rows):
    rows = sections_to_rows(commscope_json, source="EMSS")
    assert len(rows) == 12
    assert len(golden_rows) == 12
    for got, want in zip(rows, golden_rows):
        for col in COLUMNS:
            assert got[col] == want[col], (col, got[col], want[col])


def test_number_of_ports_is_derived(commscope_json):
    rows = sections_to_rows(commscope_json)
    assert rows[0]["Section Ports"] == "1,2,5,6"
    assert rows[0]["Number of Ports"] == "4"


def test_manufacturer_model_and_source_passthrough(commscope_json):
    rows = sections_to_rows(commscope_json, manufacturer="Acme", model_name="X1", source="NAD")
    assert rows[0]["Antenna manufacturer"] == "Acme"
    assert rows[0]["Model"] == "X1"
    assert rows[0]["Antenna Source"] == "NAD"  # supplied by caller, not hard-coded


def test_source_blank_when_not_supplied(commscope_json):
    # The row expander has no hard-coded default; a missing source is just blank here
    # (the default is resolved one layer up, from the workbook source vocabulary).
    rows = sections_to_rows(commscope_json)
    assert rows[0]["Antenna Source"] == ""


def test_to_cell_str_trims_whole_floats():
    assert to_cell_str(27.0) == "27"
    assert to_cell_str(-27.0) == "-27"
    assert to_cell_str(13.7) == "13.7"
    assert to_cell_str(None) == ""
    assert to_cell_str("  panel ") == "panel"


def test_tilt_and_port_helpers():
    assert parse_tilt_range("2 to 20") == (2.0, 20.0)
    assert parse_tilt_range("5") == (5.0, 5.0)
    assert parse_tilt_range("") is None
    assert parse_ports("1,2,5,6") == ["1", "2", "5", "6"]
    assert parse_ports(" ") == []


def test_normalize_tilt_to_canonical_form():
    assert normalize_tilt("2-20") == "2 to 20"
    assert normalize_tilt("2 to 20") == "2 to 20"
    assert normalize_tilt("2–12") == "2 to 12"   # en dash
    assert normalize_tilt("2 deg to 12 deg") == "2 to 12"
    assert normalize_tilt("6") == "6"
    assert normalize_tilt("") == ""
    assert normalize_tilt("2,6,10") == "2,6,10"   # discrete options, NOT a range
    assert normalize_tilt("2, 10") == "2,10"      # two discrete options, NOT "2 to 10"


def test_normalize_ports_separators():
    assert normalize_ports("1, 2, 5, 6") == "1,2,5,6"
    assert normalize_ports("1/2/5/6") == "1,2,5,6"
    assert normalize_ports("9 10 13 14") == "9,10,13,14"
    assert normalize_ports("") == ""


def test_min_max_blanked_for_named_band():
    data = {"sections": [{
        "frequency": "750 MHz", "minFreqHz": "698000000", "maxFreqHz": "806000000",
        "tilts": "2-20", "ports": "1, 2",
    }]}
    row = sections_to_rows(data)[0]
    assert row["Min Freq [Hz]"] == ""
    assert row["Max Freq [Hz]"] == ""
    assert row["Tilts [0,1,2,3]"] == "2 to 20"
    assert row["Section Ports"] == "1,2"
    assert row["Number of Ports"] == "2"
    assert row["Aperture Diameter [m]"] == ""


def test_min_max_kept_for_custom():
    data = {"sections": [{
        "frequency": "Custom", "minFreqHz": "700000000", "maxFreqHz": "800000000", "ports": "1",
    }]}
    row = sections_to_rows(data)[0]
    assert row["Min Freq [Hz]"] == "700000000"
    assert row["Max Freq [Hz]"] == "800000000"
