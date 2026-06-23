import json

from antenna_reader.store import SessionLog, build_report


def test_session_log_records_and_report(tmp_path):
    log = SessionLog("abc123def456", b"%PDF-1.4 fake", "commscope.pdf",
                     "CommScope", "", "claude-sonnet-4-6", base_dir=tmp_path)
    log.log_extraction(
        [{"Frequency": "750 MHz"}, {"Frequency": "850 MHz band"}],
        [{"Tilts [0,1,2,3]": "Unparseable tilt value"}, {}],
    )
    log.log_refine("tilts should read 2 to 20", "Reformatted the tilt values.",
                   [{"Frequency": "750 MHz"}, {"Frequency": "850 MHz band"}], [{}, {}])
    log.log_download([{"Frequency": "750 MHz"}, {"Frequency": "850 MHz band"}])

    rec = json.loads((log.dir / "record.json").read_text(encoding="utf-8"))
    assert rec["accepted"] is True
    assert (log.dir / "datasheet.pdf").exists()
    kinds = [t["kind"] for t in rec["turns"]]
    assert kinds == ["extract", "refine"]
    assert rec["turns"][0]["flag_summary"] == {"Tilts [0,1,2,3]": 1}

    report = build_report(tmp_path)
    assert "tilts should read 2 to 20" in report          # the correction is surfaced
    assert "Tilts [0,1,2,3]" in report                    # the failure column is tallied


def test_report_empty(tmp_path):
    assert "No logged sessions" in build_report(tmp_path / "nope")
