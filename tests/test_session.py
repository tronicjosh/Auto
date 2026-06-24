import antenna_reader.session as sess_mod
from antenna_reader import settings
from antenna_reader.session import DatasheetSession
from antenna_reader.workflows import get_workflow


class _FakeConv:
    """Stands in for the Anthropic conversation so the session state machine is tested offline."""

    def __init__(self, *a, **k):
        self.calls = [{"cost_usd": 0.06}]
        self._data = {"manufacturer": "CommScope", "model": "M", "type": "panel",
                      "sections": [{"frequency": "750 MHz", "minFreqHz": "", "maxFreqHz": "",
                                    "tilts": "2 to 8", "ports": "1,2,5,6", "azimuth": 0,
                                    "gain_dbi": 13.7, "hbw_deg": 60, "vbw_deg": 7}]}

    def extract(self):
        return self._data

    def refine(self, feedback):
        self.calls.append({"cost_usd": 0.03})
        d = dict(self._data)
        d["sections"] = [dict(self._data["sections"][0], gain_dbi=14.0)]
        return d, "bumped gain"

    def discard_last_turn(self):
        pass


def _make(monkeypatch):
    monkeypatch.setattr(sess_mod, "Conversation", _FakeConv)
    wf = get_workflow("antenna")
    return DatasheetSession(wf, b"%PDF-fake", source="EMSS", profile_key="panel",
                            profile_label="Panel", classify_cost={"cost_usd": 0.01})


def test_extract_produces_rows_version_and_cost(monkeypatch):
    s = _make(monkeypatch)
    v0 = s.extract()
    assert v0["index"] == 0 and len(v0["rows"]) == 1
    assert s.current_rows()[0]["Frequency"] == "750 MHz"
    assert s.current_rows()[0]["Antenna Source"] == "EMSS"
    assert s.cost()["n_calls"] == 2          # classify + extract
    assert s.cost()["total_usd"] == 0.07     # 0.01 classify + 0.06 extract


def test_refine_approve_then_revert(monkeypatch):
    s = _make(monkeypatch)
    s.extract()
    pending, diff = s.refine("bump gain")
    assert s.pending is not None
    s.approve()
    assert s.pending is None and len(s.versions) == 2
    s.refine("again")
    s.revert()
    assert s.pending is None and len(s.versions) == 2  # revert dropped the pending


def test_write_produces_dropdown_preserving_xlsx(monkeypatch, tmp_path):
    s = _make(monkeypatch)
    s.extract()
    out = tmp_path / "nested" / "batch.xlsx"   # parent auto-created
    s.write(out)
    assert out.exists()
    assert out.read_bytes()[:2] == b"PK"        # a valid xlsx (zip) with dropdowns


def test_settings_read_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("IXUS_BATCH_SHEET", str(tmp_path / "sheet.xlsx"))
    monkeypatch.setenv("IXUS_TEMPLATE", str(tmp_path / "template.xlsx"))
    assert settings.batch_sheet_path() == tmp_path / "sheet.xlsx"
    assert settings.template_path() == tmp_path / "template.xlsx"
    assert "batch_sheet" in settings.summary() and "api_key_set" in settings.summary()
