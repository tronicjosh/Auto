import hashlib
import re
import shutil
import zipfile
from pathlib import Path

from autobulksheet import settings
from autobulksheet.workbook import _find_descriptions_sheet_path, verify_output, write_populated

TEMPLATE_PATH = settings.template_path()   # the fixture workbook (IXUS_TEMPLATE set in conftest)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _desc_xml(source):
    with zipfile.ZipFile(source) as z:
        return z.read(_find_descriptions_sheet_path(z)).decode("utf-8")


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


# --- update-in-place (one workbook is both the source and the output) --- #

def test_update_in_place_refills_an_already_populated_workbook(tmp_path, golden_rows):
    """Re-filling a workbook that already has antenna rows must give the SAME result as filling
    the empty template — i.e. the old rows are cleared and the structure stays pristine."""
    fresh = tmp_path / "fresh.xlsx"
    write_populated(TEMPLATE_PATH, golden_rows[:3], fresh)          # empty -> 3 rows

    twelve = tmp_path / "twelve.xlsx"
    write_populated(TEMPLATE_PATH, golden_rows, twelve)            # empty -> 12 rows
    refilled = tmp_path / "refilled.xlsx"
    write_populated(twelve, golden_rows[:3], refilled)            # 12-populated -> 3 rows

    assert _desc_xml(refilled) == _desc_xml(fresh)                # reset is perfect
    info = verify_output(TEMPLATE_PATH, refilled)
    assert info["filled_rows"] == 3 and info["has_dropdowns"] and info["members_match"]


def test_update_in_place_same_file_across_runs(tmp_path, golden_rows):
    """IXUS_TEMPLATE == IXUS_BATCH_SHEET: write into one live file, repeatedly."""
    live = tmp_path / "live.xlsx"
    shutil.copy(TEMPLATE_PATH, live)

    write_populated(live, golden_rows[:5], live)                  # template == output == live
    assert verify_output(TEMPLATE_PATH, live)["filled_rows"] == 5

    write_populated(live, golden_rows[:2], live)                  # run again on the same file
    info = verify_output(TEMPLATE_PATH, live)
    assert info["filled_rows"] == 2 and info["has_dropdowns"] and info["members_match"]


def test_update_in_place_reverses_prior_growth(tmp_path, golden_rows):
    """After a >29-row run grew the sheet, a later smaller run drops the appended rows and
    shrinks the ranges back to base."""
    big = (golden_rows * 4)[:35]                                  # >30 -> grows the sheet
    grown = tmp_path / "grown.xlsx"
    write_populated(TEMPLATE_PATH, big, grown)
    assert verify_output(TEMPLATE_PATH, grown)["filled_rows"] == 35

    out = tmp_path / "out.xlsx"
    write_populated(grown, golden_rows[:3], out)                 # re-fill the grown file with 3
    fresh = tmp_path / "fresh.xlsx"
    write_populated(TEMPLATE_PATH, golden_rows[:3], fresh)
    assert _desc_xml(out) == _desc_xml(fresh)                    # pristine even after growth
    assert verify_output(TEMPLATE_PATH, out)["filled_rows"] == 3
