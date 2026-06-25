from autobulksheet.rows import sections_to_rows
from autobulksheet.schema import COLUMNS


def _key(row):
    return tuple(row[c] for c in COLUMNS)


def test_offline_acceptance_matches_golden(commscope_json, golden_rows):
    """The saved extraction JSON, expanded, reproduces the golden CSV exactly."""
    rows = sections_to_rows(commscope_json, source="EMSS")
    assert {_key(r) for r in rows} == {_key(r) for r in golden_rows}
