"""The vocabulary write-back patches the workbook in memory only; these tests never
touch the real template on disk."""

import io
import re
import zipfile

from antenna_reader.config import TEMPLATE_PATH
from antenna_reader.vocab import read_vocabularies
from antenna_reader.vocab_writer import _find_sheet_path, patch_vocab, verify_patched


def _dropdown_end(xlsx_bytes, col):
    z = zipfile.ZipFile(io.BytesIO(xlsx_bytes))
    desc = z.read(_find_sheet_path(z, "Descriptions")).decode("utf-8")
    ends = re.findall(r"Data_Validation!\$%s\$\d+:\$%s\$(\d+)" % (col, col), desc)
    return {int(e) for e in ends}


def test_grow_source_preserves_others_and_dropdowns():
    before = read_vocabularies(TEMPLATE_PATH)
    edits = {"source": before["source"] + ["AUDIT"]}
    patched = patch_vocab(TEMPLATE_PATH, edits)

    facts = verify_patched(patched, edits)
    assert facts["ok"], facts
    after = read_vocabularies(io.BytesIO(patched))
    assert after["source"] == before["source"] + ["AUDIT"]
    assert after["manufacturers"] == before["manufacturers"]   # untouched columns preserved
    assert after["type"] == before["type"]
    # source dropdown range end-row grew by one (data starts at row 2)
    assert _dropdown_end(patched, "I") == {len(after["source"]) + 1}


def test_shrink_frequency_resyncs_range():
    before = read_vocabularies(TEMPLATE_PATH)
    shorter = before["frequency"][:-2]
    patched = patch_vocab(TEMPLATE_PATH, {"frequency": shorter})
    after = read_vocabularies(io.BytesIO(patched))
    assert after["frequency"] == shorter
    assert _dropdown_end(patched, "C") == {len(shorter) + 1}


def test_member_set_is_identical_and_dropdowns_intact():
    patched = patch_vocab(TEMPLATE_PATH, {"source": ["EMSS", "NAD"]})
    with zipfile.ZipFile(TEMPLATE_PATH) as zt, zipfile.ZipFile(io.BytesIO(patched)) as zp:
        assert set(zt.namelist()) == set(zp.namelist())   # nothing added/dropped
        desc = zp.read(_find_sheet_path(zp, "Descriptions")).decode("utf-8")
        assert "<x14:dataValidations" in desc             # the x14 dropdowns survive


def test_verify_rejects_a_mismatch():
    patched = patch_vocab(TEMPLATE_PATH, {"source": ["EMSS", "NAD"]})
    # Asking verify to confirm an edit that wasn't applied must fail the safety gate.
    assert verify_patched(patched, {"source": ["SOMETHING_ELSE"]})["ok"] is False
