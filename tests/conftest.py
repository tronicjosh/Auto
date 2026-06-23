import csv
import json
from pathlib import Path

import pytest

from antenna_reader.config import TEMPLATE_PATH

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def template_path():
    return TEMPLATE_PATH


@pytest.fixture
def golden_rows():
    """The known-good 12 CommScope rows, as dicts keyed by the column headers."""
    with open(FIXTURES / "frequency_band_data.csv", newline="", encoding="utf-8") as f:
        rows = [{k: (v or "") for k, v in r.items()} for r in csv.DictReader(f)]
    # Drop any blank trailing rows.
    return [r for r in rows if any(str(v).strip() for v in r.values())]


@pytest.fixture
def commscope_json():
    return json.loads((FIXTURES / "2NN2HH-33B-R4.extraction.json").read_text(encoding="utf-8"))


@pytest.fixture
def vocab(template_path):
    from antenna_reader.vocab import read_vocabularies
    return read_vocabularies(template_path)
