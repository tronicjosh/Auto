from antenna_reader.workflows.diff import diff_versions

COLS = ["Frequency", "Gain [dBi]", "Section Ports"]
KEYS = ["Frequency", "Section Ports"]


def test_changed_cell():
    prev = [{"Frequency": "750 MHz", "Gain [dBi]": "13", "Section Ports": "1,2"}]
    new = [{"Frequency": "750 MHz", "Gain [dBi]": "14", "Section Ports": "1,2"}]
    d = diff_versions(prev, new, COLS, KEYS)
    assert d["changed"] == [{"row": 0, "column": "Gain [dBi]"}]
    assert d["added_rows"] == [] and d["removed_rows"] == []


def test_added_and_removed_rows():
    prev = [{"Frequency": "750 MHz", "Section Ports": "1,2"}]
    new = [{"Frequency": "850 MHz band", "Section Ports": "3,4"}]
    d = diff_versions(prev, new, COLS, KEYS)
    assert d["added_rows"] == [0]
    assert d["removed_rows"] == [0]


def test_reorder_is_not_a_change():
    a = {"Frequency": "750 MHz", "Gain [dBi]": "13", "Section Ports": "1,2"}
    b = {"Frequency": "850 MHz band", "Gain [dBi]": "14", "Section Ports": "3,4"}
    d = diff_versions([a, b], [b, a], COLS, KEYS)
    assert d == {"changed": [], "added_rows": [], "removed_rows": []}


def test_index_fallback_when_keys_blank():
    prev = [{"Frequency": "", "Section Ports": "", "Gain [dBi]": "1"}]
    new = [{"Frequency": "", "Section Ports": "", "Gain [dBi]": "2"}]
    d = diff_versions(prev, new, COLS, KEYS)
    assert d["changed"] == [{"row": 0, "column": "Gain [dBi]"}]
