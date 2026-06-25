from autobulksheet.classify import _match_profile

PROFILES = [{"key": "panel", "label": "Panel"}, {"key": "omni", "label": "Omni"},
            {"key": "lens", "label": "Lens"},
            {"key": "parabolic", "label": "Parabolic reflector"},
            {"key": "custom", "label": "Custom"}]


def test_matches_each_type():
    assert _match_profile("Panel - rectangular radome", PROFILES) == ("panel", "Panel")
    assert _match_profile("Parabolic reflector, it's a dish", PROFILES) == ("parabolic", "Parabolic reflector")
    assert _match_profile("Omni\nbecause cylindrical", PROFILES) == ("omni", "Omni")
    assert _match_profile("Custom", PROFILES) == ("custom", "Custom")


def test_first_line_wins_over_negation_in_body():
    # The answer is on the first line; "not a panel" in the body must not flip it.
    assert _match_profile("Omni\nThis is not a panel antenna.", PROFILES) == ("omni", "Omni")


def test_no_match_returns_none():
    assert _match_profile("I cannot tell from this page", PROFILES) == (None, None)
