import csv
import json
import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

# The template is no longer bundled in the project — production supplies it via IXUS_TEMPLATE.
# Point the env var at the fixture workbook so the writer/vocab tests have a real one to use.
# (setdefault runs at conftest import, before any test imports autobulksheet.)
os.environ.setdefault("IXUS_TEMPLATE", str(FIXTURES / "ixus_template.xlsx"))


@pytest.fixture
def template_path():
    from autobulksheet import settings
    return settings.template_path()


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
    from autobulksheet.vocab import read_vocabularies
    return read_vocabularies(template_path)
