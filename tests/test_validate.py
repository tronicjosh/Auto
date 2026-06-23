from antenna_reader.schema import COLUMNS
from antenna_reader.validate import validate_rows

VOCAB = {
    "frequency": ["Custom", "750 MHz", "850 MHz band", "1800 MHz band",
                  "1.95 GHz", "2100 MHz band", "2.35 GHz"],
    "type": ["panel", "omni"],
}


def blank(**kw):
    row = {c: "" for c in COLUMNS}
    row.update(kw)
    return row


def test_clean_row_has_no_flags():
    row = blank(Frequency="750 MHz", Type="panel",
                **{"Section Ports": "1,2,5,6", "Number of Ports": "4",
                   "Tilts [0,1,2,3]": "2 to 20", "Gain [dBi]": "13.7",
                   "Horizontal HPBW [deg]": "42", "Vertical HPBW [deg]": "23.7"})
    assert validate_rows([row], VOCAB)[0] == {}


def test_bad_frequency_and_type_flagged():
    row = blank(Frequency="700 MHz", Type="panl")
    flags = validate_rows([row], VOCAB)[0]
    assert "Frequency" in flags
    assert "Type" in flags


def test_port_count_mismatch():
    row = blank(**{"Section Ports": "1,2,3", "Number of Ports": "4"})
    assert "Number of Ports" in validate_rows([row], VOCAB)[0]


def test_min_freq_only_for_custom():
    row = blank(Frequency="750 MHz", **{"Min Freq [Hz]": "700000000"})
    assert "Min Freq [Hz]" in validate_rows([row], VOCAB)[0]
    custom = blank(Frequency="Custom", **{"Min Freq [Hz]": "700000000"})
    assert "Min Freq [Hz]" not in validate_rows([custom], VOCAB)[0]


def test_tilt_range_rules():
    assert "Tilts [0,1,2,3]" in validate_rows([blank(**{"Tilts [0,1,2,3]": "20 to 2"})], VOCAB)[0]
    assert "Tilts [0,1,2,3]" in validate_rows([blank(**{"Tilts [0,1,2,3]": "-1 to 5"})], VOCAB)[0]
    assert "Tilts [0,1,2,3]" not in validate_rows([blank(**{"Tilts [0,1,2,3]": "2 to 20"})], VOCAB)[0]
    # discrete tilt options are valid (not flagged); a negative one is flagged
    assert "Tilts [0,1,2,3]" not in validate_rows([blank(**{"Tilts [0,1,2,3]": "2,6,10"})], VOCAB)[0]
    assert "Tilts [0,1,2,3]" in validate_rows([blank(**{"Tilts [0,1,2,3]": "2,-6,10"})], VOCAB)[0]


def test_duplicate_ports_same_frequency_flagged_on_both():
    r1 = blank(Frequency="750 MHz", **{"Section Ports": "1,2", "Number of Ports": "2"})
    r2 = blank(Frequency="750 MHz", **{"Section Ports": "2,3", "Number of Ports": "2"})
    flags = validate_rows([r1, r2], VOCAB)
    assert "Section Ports" in flags[0]
    assert "Section Ports" in flags[1]


def test_implausible_gain_flagged():
    # HBW*VBW small but gain tiny -> large directivity-gain delta -> flagged.
    row = blank(**{"Gain [dBi]": "2", "Horizontal HPBW [deg]": "33", "Vertical HPBW [deg]": "7.3"})
    assert "Gain [dBi]" in validate_rows([row], VOCAB)[0]
