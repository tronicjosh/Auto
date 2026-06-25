from autobulksheet.engine import apply_type_guardrails

_COLS = ["Tilts [0,1,2,3]", "Number of Ports", "Aperture Diameter [m]",
         "Horizontal HPBW [deg]", "Vertical HPBW [deg]", "Azimuth Rotation"]

PARABOLIC = [
    {"column": "Tilts [0,1,2,3]", "equals": "0", "message": "tilt 0"},
    {"column": "Number of Ports", "equals": "1", "message": "1 port"},
    {"column": "Aperture Diameter [m]", "required": True, "message": "need aperture"},
    {"columns_equal": ["Horizontal HPBW [deg]", "Vertical HPBW [deg]"], "message": "H=V"},
]


def _row(**kw):
    r = {c: "" for c in _COLS}
    r.update(kw)
    return r


def test_parabolic_clean_row_has_no_guardrail_flags():
    r = _row(**{"Tilts [0,1,2,3]": "0", "Number of Ports": "1",
                "Aperture Diameter [m]": "0.6", "Horizontal HPBW [deg]": "5",
                "Vertical HPBW [deg]": "5"})
    assert apply_type_guardrails([r], [{}], PARABOLIC)[0] == {}


def test_parabolic_violations_flagged():
    r = _row(**{"Tilts [0,1,2,3]": "2", "Number of Ports": "4",
                "Aperture Diameter [m]": "", "Horizontal HPBW [deg]": "5",
                "Vertical HPBW [deg]": "7"})
    f = apply_type_guardrails([r], [{}], PARABOLIC)[0]
    assert "Tilts [0,1,2,3]" in f
    assert "Number of Ports" in f
    assert "Aperture Diameter [m]" in f
    assert "Horizontal HPBW [deg]" in f and "Vertical HPBW [deg]" in f


def test_equals_is_numeric_tolerant():
    # "0.0" satisfies equals "0"; "5.0" equals "5".
    r = _row(**{"Tilts [0,1,2,3]": "0.0", "Number of Ports": "1",
                "Aperture Diameter [m]": "1", "Horizontal HPBW [deg]": "5",
                "Vertical HPBW [deg]": "5.0"})
    assert apply_type_guardrails([r], [{}], PARABOLIC)[0] == {}


def test_blank_guardrail_both_directions():
    rails = [{"column": "Aperture Diameter [m]", "blank": True, "message": "no aperture"}]
    assert "Aperture Diameter [m]" in apply_type_guardrails(
        [_row(**{"Aperture Diameter [m]": "0.5"})], [{}], rails)[0]
    assert apply_type_guardrails([_row()], [{}], rails)[0] == {}


def test_guardrails_do_not_clobber_existing_flag():
    rails = [{"column": "Tilts [0,1,2,3]", "equals": "0", "message": "tilt 0"}]
    f = apply_type_guardrails([_row(**{"Tilts [0,1,2,3]": "2"})], [{"Tilts [0,1,2,3]": "earlier"}], rails)
    assert f[0]["Tilts [0,1,2,3]"] == "earlier"  # base validation flag preserved
