from starlette.testclient import TestClient

from antenna_reader.web import app

client = TestClient(app)


def test_index_serves_and_lists_workflows():
    assert client.get("/").status_code == 200
    workflows = client.get("/workflows").json()["workflows"]
    assert any(w["id"] == "antenna" and w["enabled"] for w in workflows)


def test_download_accepts_raw_rows():
    rows = [{"Antenna Source": "EMSS", "Frequency": "750 MHz", "Gain [dBi]": "13.7",
             "Section Ports": "1,2,5,6", "Number of Ports": "4"}]
    r = client.post("/download", json={"rows": rows})
    assert r.status_code == 200
    assert r.content[:2] == b"PK"  # valid xlsx (zip) with dropdowns preserved


def test_refine_unknown_session_404():
    assert client.post("/refine", json={"session_id": "nope", "message": "x"}).status_code == 404


def test_workflow_definition_endpoint():
    d = client.get("/workflows/antenna").json()
    assert d["id"] == "antenna"
    assert len(d["columns"]) == 18
    assert d["rules"]
    assert any(s["key"] == "bands" for s in d["config_sections"])  # generic section schema
    assert d["section_data"].get("bands")                          # its rows
    assert "Respond ONLY with JSON" in d["prompt"]                 # the real prompt, rendered
    assert "[[FREQUENCY_VOCAB]]" in d["prompt_template"]           # editable template has the tags
    assert "ui" in d and d["ui"].get("header_title")
    assert client.get("/workflows/nope").status_code == 404


def test_vocab_save_writes_workbook_then_restore():
    """End-to-end: editing a vocabulary in the UI writes it back into the workbook.
    The real template is modified, so we snapshot and restore it byte-for-byte."""
    from antenna_reader.config import TEMPLATE_PATH
    from antenna_reader.workflows import reload_workflow

    original = TEMPLATE_PATH.read_bytes()
    bak = TEMPLATE_PATH.with_name(TEMPLATE_PATH.name + ".bak")
    try:
        before = client.get("/workflows/antenna").json()["vocab"]["source"]
        payload = {"vocab": {"source": before + ["ZZAUDIT"]}}
        r = client.post("/workflows/antenna/vocab", json=payload)
        assert r.status_code == 200, r.text
        assert r.json()["vocab"]["source"] == before + ["ZZAUDIT"]
        # persisted to the workbook + reloaded into the live registry
        assert "ZZAUDIT" in client.get("/workflows/antenna").json()["vocab"]["source"]
        # emptying a vocabulary is refused
        assert client.post("/workflows/antenna/vocab", json={"vocab": {"source": []}}).status_code == 400
    finally:
        TEMPLATE_PATH.write_bytes(original)
        if bak.exists():
            bak.unlink()
        reload_workflow("antenna")

    assert "ZZAUDIT" not in client.get("/workflows/antenna").json()["vocab"]["source"]


def test_save_add_table_roundtrip_and_reload():
    from antenna_reader.config import PROJECT_ROOT
    from antenna_reader.workflows import reload_workflow

    cdir = PROJECT_ROOT / "workflow_configs" / "antenna"
    originals = {p.name: p.read_bytes() for p in cdir.iterdir() if p.is_file()}
    had_taxfile = (cdir / "tax_codes.json").exists()
    try:
        d = client.get("/workflows/antenna").json()
        # Add a brand-new config table from scratch and reference it in the prompt.
        new_sections = d["config_sections"] + [{
            "key": "tax_codes", "title": "Tax codes", "help": "", "inject_tag": "[[TAX_CODES]]",
            "intro": "Tax codes:", "row_template": "- {code}: {rate}",
            "columns": [{"key": "code", "label": "Code", "type": "text"},
                        {"key": "rate", "label": "Rate", "type": "text"}],
        }]
        new_data = dict(d["section_data"]); new_data["tax_codes"] = [{"code": "VAT", "rate": "15%"}]
        payload = {
            "title": d["title"], "description": d["description"], "ui": d["ui"],
            "rules": d["rules"] + ["TEST RULE XYZ"],
            "config_sections": new_sections, "section_data": new_data,
            "prompt": d["prompt_template"] + "\n[[TAX_CODES]]\n",
        }
        r = client.post("/workflows/antenna", json=payload)
        assert r.status_code == 200
        d2 = r.json()
        assert "TEST RULE XYZ" in d2["rules"]
        assert any(s["key"] == "tax_codes" for s in d2["config_sections"])
        assert d2["section_data"]["tax_codes"] == [{"code": "VAT", "rate": "15%"}]
        assert "VAT: 15%" in d2["prompt"]   # the new table is injected into the rendered prompt
        # persisted + reloaded into the live registry
        assert any(s["key"] == "tax_codes"
                   for s in client.get("/workflows/antenna").json()["config_sections"])
    finally:
        for name, data in originals.items():
            (cdir / name).write_bytes(data)
        if not had_taxfile and (cdir / "tax_codes.json").exists():
            (cdir / "tax_codes.json").unlink()
        reload_workflow("antenna")

    assert "TEST RULE XYZ" not in client.get("/workflows/antenna").json()["rules"]
    assert client.post("/workflows/nope", json={}).status_code == 404
