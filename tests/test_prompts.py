"""Guardrails on the prompt FILES themselves — so editing base_prompt.txt / router_prompt.txt
/ profiles/*.txt can never silently break the pipeline. Run `pytest` after editing prompts:
green means every prompt still assembles (schema intact, vocab injected, no dangling tags).
No API calls — this only checks how the prompt renders.
"""

from antenna_reader.workflows import get_workflow

VOCAB = {"frequency": ["750 MHz", "Custom"],
         "type": ["panel", "omni", "parabolic reflector", "custom"],
         "manufacturers": ["CommScope", "Kathrein"], "source": ["EMSS", "NAD"]}

# Schema keys that MUST survive any base_prompt.txt edit (a missing one = broken extraction).
_SCHEMA_KEYS = ["manufacturer", "model", "type", "sections", "gain_dbi", "aperture_m"]


def test_base_prompt_keeps_the_json_schema_and_resolves_tags():
    wf = get_workflow("antenna")
    p = wf.build_prompt(VOCAB)  # no profile selected
    assert "Respond ONLY with JSON" in p
    for key in _SCHEMA_KEYS:
        assert key in p, f"base_prompt is missing schema key {key!r}"
    assert "[[" not in p, "base_prompt has an unresolved [[...]] tag"


def test_every_profile_assembles():
    wf = get_workflow("antenna")
    for prof in wf.extras["profiles"]:
        p = wf.build_prompt(VOCAB, prof["key"])
        assert "Respond ONLY with JSON" in p, f"{prof['key']}: schema dropped"
        assert "750 MHz" in p and "CommScope" in p, f"{prof['key']}: vocab not injected"
        assert prof["label"] in p, f"{prof['key']}: profile name not spliced in"
        assert "[[" not in p, f"{prof['key']}: unresolved tag"


def test_profiles_are_distinct_and_carry_their_rules():
    wf = get_workflow("antenna")
    panel = wf.build_prompt(VOCAB, "panel")
    omni = wf.build_prompt(VOCAB, "omni")
    parabolic = wf.build_prompt(VOCAB, "parabolic")
    assert panel != omni != parabolic
    assert "rectangular radome" in panel        # panel's own rule
    assert "360" in omni                        # omni HPBW rule
    assert "dish diameter" in parabolic         # parabolic rule
    assert "rectangular radome" not in parabolic  # no cross-contamination


def test_router_prompt_lists_every_profile():
    wf = get_workflow("antenna")
    rp = wf.extras["router_prompt"]
    assert rp
    for prof in wf.extras["profiles"]:
        assert prof["label"] in rp, f"router_prompt never mentions {prof['label']!r}"


def test_guardrails_reference_only_real_profiles():
    wf = get_workflow("antenna")
    keys = {p["key"] for p in wf.extras["profiles"]}
    for k in wf.extras["type_guardrails"]:
        assert k in keys, f"type_guardrails has unknown profile {k!r}"
