"""Opt-in test that hits the real Claude API. Skipped unless ANTHROPIC_API_KEY is set.

    pytest -m live
"""

import os

import pytest

from antenna_reader.config import PROJECT_ROOT
from antenna_reader.pipeline import process_pdf

PDF = PROJECT_ROOT / "data" / "datasheets" / "commscope_2NN2HH-33B-R4.pdf"


def _identity(row):
    # Fields that should match exactly regardless of small numeric transcription noise.
    return (row["Frequency"], row["Azimuth Rotation"], row["Section Ports"])


@pytest.mark.live
@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"),
                    reason="ANTHROPIC_API_KEY not set")
def test_live_commscope_matches_golden(golden_rows, tmp_path):
    result = process_pdf(PDF, manufacturer="CommScope", out_path=tmp_path / "live.xlsx")
    rows = result["rows"]

    assert len(rows) == 12, f"expected 12 rows, got {len(rows)}"
    assert {_identity(r) for r in rows} == {_identity(r) for r in golden_rows}

    # The output workbook must keep its dropdowns.
    assert result["verify"]["has_dropdowns"]
    assert result["verify"]["members_match"]
