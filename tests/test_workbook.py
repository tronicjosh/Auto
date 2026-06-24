import hashlib
import re
import zipfile
from pathlib import Path

from antenna_reader import settings
from antenna_reader.workbook import verify_output, write_populated

TEMPLATE_PATH = settings.template_path()   # the fixture workbook (IXUS_TEMPLATE set in conftest)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_write_preserves_dropdowns_and_structure(tmp_path, golden_rows):
    before = _sha(TEMPLATE_PATH)
    out = tmp_path / "out.xlsx"
    write_populated(TEMPLATE_PATH, golden_rows, out)

    # The master template must be untouched.
    assert _sha(TEMPLATE_PATH) == before

    info = verify_output(TEMPLATE_PATH, out)
    assert info["members_match"]
    assert info["has_dropdowns"]
    assert info["filled_rows"] == 12

    with zipfile.ZipFile(out) as z:
        sheet = z.read(info["sheet_path"]).decode("utf-8")
    # E2 is the Frequency text cell; L2 the numeric gain cell.
    assert ">750 MHz<" in sheet
    assert re.search(r'<c r="L2"[^>]*><v>13.7</v></c>', sheet)
    # The x14 extLst (dropdowns) survived — manufacturer range intact (end row tracks the
    # vocab size, so match the pattern rather than a fixed row).
    assert re.search(r"Data_Validation!\$A\$2:\$A\$\d+", sheet)


def test_growth_beyond_29_rows(tmp_path, golden_rows):
    rows = (golden_rows * 3)[:31]  # 31 rows > the 29 pre-styled slots
    out = tmp_path / "grow.xlsx"
    write_populated(TEMPLATE_PATH, rows, out)

    info = verify_output(TEMPLATE_PATH, out)
    assert info["filled_rows"] == 31
    assert info["has_dropdowns"]

    with zipfile.ZipFile(out) as z:
        sheet = z.read(info["sheet_path"]).decode("utf-8")
    assert '<dimension ref="A1:R32"/>' in sheet
    assert "A2:A32" in sheet  # manufacturer dropdown range extended
