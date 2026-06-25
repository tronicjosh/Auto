"""The deterministic band-gain selection: given the model's raw datasheet-column transcription,
the code picks the highest-gain OVERLAPPING column per IXUS band and uses its matched set.
This is the logic the LLM kept getting wrong — here it is exact and tested."""

from autobulksheet.engine import select_overlapping_band_gains

# IXUS bands (name -> Hz), a subset.
BANDS = [
    {"name": "650 MHz", "min_hz": 617000000, "max_hz": 697000000},
    {"name": "750 MHz", "min_hz": 703000000, "max_hz": 803000000},
    {"name": "850 MHz band", "min_hz": 824000000, "max_hz": 894000000},
]
SPEC = {"source_field": "datasheet_bands", "unit": "mhz", "freq_column": "Frequency",
        "gain_column": "Gain [dBi]", "hbw_column": "Horizontal HPBW [deg]",
        "vbw_column": "Vertical HPBW [deg]"}


def _row(freq, gain="", hbw="", vbw=""):
    return {"Frequency": freq, "Gain [dBi]": gain,
            "Horizontal HPBW [deg]": hbw, "Vertical HPBW [deg]": vbw}


def test_850_partial_overlap_picks_higher_gain_matched_set():
    # The exact case that kept failing: 850 (824-894) overlaps 824-894 (15.8) AND 880-960 (16.0).
    data = {"datasheet_bands": [
        {"min_mhz": 824, "max_mhz": 894, "gain_dbi": 15.8, "hbw_deg": 65, "vbw_deg": 8},
        {"min_mhz": 880, "max_mhz": 960, "gain_dbi": 16.0, "hbw_deg": 60, "vbw_deg": 8.5},
    ]}
    rows = select_overlapping_band_gains([_row("850 MHz band")], data, BANDS, SPEC)
    assert rows[0]["Gain [dBi]"] == "16"
    assert rows[0]["Horizontal HPBW [deg]"] == "60"
    assert rows[0]["Vertical HPBW [deg]"] == "8.5"


def test_750_reaches_into_higher_gain_neighbour():
    data = {"datasheet_bands": [
        {"min_mhz": 690, "max_mhz": 803, "gain_dbi": 14.0, "hbw_deg": 68, "vbw_deg": 10},
        {"min_mhz": 790, "max_mhz": 862, "gain_dbi": 15.5, "hbw_deg": 65, "vbw_deg": 9.5},
    ]}
    rows = select_overlapping_band_gains([_row("750 MHz")], data, BANDS, SPEC)
    assert rows[0]["Gain [dBi]"] == "15.5"
    assert rows[0]["Horizontal HPBW [deg]"] == "65"
    assert rows[0]["Vertical HPBW [deg]"] == "9.5"


def test_equal_gain_tie_break_picks_wider_horizontal_beamwidth():
    # 850 (824-894) overlaps two columns with the SAME gain (16.0); the wider HBW (65) wins,
    # and its matched vertical beamwidth comes with it.
    data = {"datasheet_bands": [
        {"min_mhz": 824, "max_mhz": 894, "gain_dbi": 16.0, "hbw_deg": 65, "vbw_deg": 8},
        {"min_mhz": 880, "max_mhz": 960, "gain_dbi": 16.0, "hbw_deg": 60, "vbw_deg": 8.5},
    ]}
    rows = select_overlapping_band_gains([_row("850 MHz band")], data, BANDS, SPEC)
    assert rows[0]["Gain [dBi]"] == "16"
    assert rows[0]["Horizontal HPBW [deg]"] == "65"   # wider HBW wins the gain tie
    assert rows[0]["Vertical HPBW [deg]"] == "8"


def test_non_overlapping_columns_are_ignored():
    data = {"datasheet_bands": [
        {"min_mhz": 824, "max_mhz": 894, "gain_dbi": 15.0, "hbw_deg": 65, "vbw_deg": 8},
        {"min_mhz": 1700, "max_mhz": 2200, "gain_dbi": 18.0, "hbw_deg": 45, "vbw_deg": 5},  # no overlap with 850
    ]}
    rows = select_overlapping_band_gains([_row("850 MHz band")], data, BANDS, SPEC)
    assert rows[0]["Gain [dBi]"] == "15"  # not the higher 18.0 from the non-overlapping column


def test_non_overlapping_standard_band_is_dropped():
    # The model wrongly added a 750 band, but the datasheet only covers the 850 band.
    # 750 (703-803) overlaps no transcribed column -> the row is excluded entirely.
    data = {"datasheet_bands": [
        {"min_mhz": 824, "max_mhz": 894, "gain_dbi": 15.0, "hbw_deg": 65, "vbw_deg": 8},
    ]}
    rows = select_overlapping_band_gains(
        [_row("750 MHz", gain="13", hbw="60", vbw="9"), _row("850 MHz band")], data, BANDS, SPEC)
    assert [r["Frequency"] for r in rows] == ["850 MHz band"]  # 750 dropped, 850 kept
    assert rows[0]["Gain [dBi]"] == "15"


def test_omitted_overlapping_band_is_added_cloning_sibling_port_group():
    # One datasheet column (780-900) overlaps BOTH the 750 and 850 IXUS bands, but the model only
    # emitted 750. The 850 band must be ADDED, cloning 750's port group (they share the column).
    data = {"datasheet_bands": [
        {"min_mhz": 780, "max_mhz": 900, "gain_dbi": 16.0, "hbw_deg": 60, "vbw_deg": 8},
    ]}
    row750 = {"Frequency": "750 MHz", "Section Ports": "1,2", "Number of Ports": "2",
              "Tilts [0,1,2,3]": "2 to 8", "Azimuth Rotation": "0",
              "Gain [dBi]": "", "Horizontal HPBW [deg]": "", "Vertical HPBW [deg]": ""}
    rows = select_overlapping_band_gains([dict(row750)], data, BANDS, SPEC)
    freqs = [r["Frequency"] for r in rows]
    assert "850 MHz band" in freqs                  # the omitted overlapping band was added
    added = next(r for r in rows if r["Frequency"] == "850 MHz band")
    assert added["Section Ports"] == "1,2"          # port group cloned from the 750 sibling
    assert added["Number of Ports"] == "2"
    assert added["Tilts [0,1,2,3]"] == "2 to 8"     # tilts cloned too
    assert added["Gain [dBi]"] == "16"              # gain from the overlapping column


def test_omitted_band_not_added_without_a_sibling_to_clone_from():
    # Only a Custom row exists (no standard-band sibling), so a band cannot be added safely.
    data = {"datasheet_bands": [{"min_mhz": 780, "max_mhz": 900, "gain_dbi": 16, "hbw_deg": 60, "vbw_deg": 8}]}
    rows = select_overlapping_band_gains([_row("Custom", gain="9.9")], data, BANDS, SPEC)
    assert [r["Frequency"] for r in rows] == ["Custom"]   # nothing invented


def test_custom_and_unknown_bands_keep_model_values():
    data = {"datasheet_bands": [{"min_mhz": 824, "max_mhz": 894, "gain_dbi": 16, "hbw_deg": 60, "vbw_deg": 8}]}
    rows = select_overlapping_band_gains(
        [_row("Custom", gain="9.9", hbw="30", vbw="30")], data, BANDS, SPEC)
    assert rows[0]["Gain [dBi]"] == "9.9"  # Custom -> untouched


def test_boundary_touch_counts_as_overlap():
    # A datasheet column starting exactly at the 750 band's upper edge (803) touches it -> counts.
    data = {"datasheet_bands": [
        {"min_mhz": 700, "max_mhz": 803, "gain_dbi": 14.0, "hbw_deg": 68, "vbw_deg": 10},
        {"min_mhz": 803, "max_mhz": 900, "gain_dbi": 17.0, "hbw_deg": 60, "vbw_deg": 7},
    ]}
    rows = select_overlapping_band_gains([_row("750 MHz")], data, BANDS, SPEC)
    assert rows[0]["Gain [dBi]"] == "17"  # touching column is in play, and it has the higher gain


def test_650_boundary_takes_greater_gain_with_matched_beamwidths():
    # 650 (617-697) overlaps a column ending at 697 AND one starting at 697 (boundary touch).
    # Take the GREATER gain and the beamwidths bonded to it.
    data = {"datasheet_bands": [
        {"min_mhz": 610, "max_mhz": 697, "gain_dbi": 14.0, "hbw_deg": 70, "vbw_deg": 12},
        {"min_mhz": 697, "max_mhz": 760, "gain_dbi": 16.0, "hbw_deg": 62, "vbw_deg": 9},
    ]}
    rows = select_overlapping_band_gains([_row("650 MHz")], data, BANDS, SPEC)
    assert rows[0]["Gain [dBi]"] == "16"              # greater of the two
    assert rows[0]["Horizontal HPBW [deg]"] == "62"   # matched set from the higher-gain band
    assert rows[0]["Vertical HPBW [deg]"] == "9"


def test_no_datasheet_bands_is_a_noop():
    rows_in = [_row("850 MHz band", gain="12", hbw="50", vbw="7")]
    rows = select_overlapping_band_gains(rows_in, {}, BANDS, SPEC)
    assert rows[0]["Gain [dBi]"] == "12"  # nothing transcribed -> leave model values
