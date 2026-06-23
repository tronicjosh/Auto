"""Write controlled vocabularies back into the workbook's Data_Validation sheet.

The dropdowns on the Descriptions sheet are x14 validations that reference ranges on
Data_Validation (e.g. source = Data_Validation!$I$2:$I$3, manufacturer = $A$2:$A$293).
To edit a vocabulary in the UI and keep the spreadsheet's dropdowns valid we must:

  1. rewrite that column's cells on Data_Validation, and
  2. resync the dropdown range's end-row on Descriptions to the new list length.

Like workbook.py, we never let openpyxl write (it strips the x14 dropdowns). We treat the
.xlsx as a zip and replace ONLY the two worksheet XML members, copying everything else
byte-for-byte. Data rows are written as inline strings, so sharedStrings.xml is untouched
(old, now-unreferenced strings simply remain — harmless). Row 1 (headers) is preserved.
"""

import io
import re
import zipfile
from xml.sax.saxutils import escape

from .config import DESCRIPTIONS_SHEET_NAME, VOCAB_SHEET_NAME
from .schema import column_letter
from .vocab import _COLUMN_MAP, read_vocabularies

# vocab key -> spreadsheet column letter on the Data_Validation sheet.
_KEY_TO_COL = {key: column_letter(col) for col, key in _COLUMN_MAP.items()}


def _find_sheet_path(zf: zipfile.ZipFile, sheet_name: str) -> str:
    """Resolve a sheet name -> its xl/worksheets/sheetN.xml member path."""
    wb_xml = zf.read("xl/workbook.xml").decode("utf-8")
    m = re.search(r'<sheet\b[^>]*\bname="%s"[^>]*\br:id="(rId\d+)"' % re.escape(sheet_name), wb_xml) \
        or re.search(r'<sheet\b[^>]*\br:id="(rId\d+)"[^>]*\bname="%s"' % re.escape(sheet_name), wb_xml)
    if not m:
        raise ValueError(f"Sheet {sheet_name!r} not found in workbook.xml")
    rid = m.group(1)
    rels = zf.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    m2 = re.search(r'<Relationship\b[^>]*\bId="%s"[^>]*\bTarget="([^"]+)"' % rid, rels) \
        or re.search(r'<Relationship\b[^>]*\bTarget="([^"]+)"[^>]*\bId="%s"' % rid, rels)
    if not m2:
        raise ValueError(f"Relationship {rid} not found in workbook rels")
    target = m2.group(1)
    return target.lstrip("/") if target.startswith("/") else "xl/" + target


def _cell(col: str, row: int, value: str) -> str:
    return (f'<c r="{col}{row}" t="inlineStr"><is>'
            f'<t xml:space="preserve">{escape(str(value))}</t></is></c>')


def _rebuild_sheetdata(dv_xml: str, lists: dict) -> str:
    """Regenerate Data_Validation rows 2.. from `lists` (key -> values); keep row 1."""
    row1 = re.search(r'<row r="1"[^>]*>.*?</row>', dv_xml, re.DOTALL)
    row1_xml = row1.group(0) if row1 else '<row r="1"/>'

    # Column letter -> ordered values for the columns we manage.
    by_col = {_KEY_TO_COL[k]: v for k, v in lists.items() if k in _KEY_TO_COL}
    max_n = max((len(v) for v in by_col.values()), default=0)

    rows = [row1_xml]
    for i in range(max_n):
        rn = i + 2
        cells = [_cell(col, rn, vals[i]) for col, vals in by_col.items() if i < len(vals)]
        if cells:
            rows.append(f'<row r="{rn}">{"".join(cells)}</row>')

    new_data = "<sheetData>" + "".join(rows) + "</sheetData>"
    dv_xml = re.sub(r'<sheetData>.*?</sheetData>', lambda _m: new_data, dv_xml, count=1, flags=re.DOTALL)
    last_row = max_n + 1
    dv_xml = re.sub(r'<dimension ref="A1:[A-Z]+\d+"/>',
                    f'<dimension ref="A1:K{last_row}"/>', dv_xml, count=1)
    return dv_xml


def _resync_dropdowns(desc_xml: str, lists: dict) -> str:
    """Grow/shrink each Descriptions dropdown range end-row to match the new list length."""
    for key, col in _KEY_TO_COL.items():
        if key not in lists:
            continue
        end = len(lists[key]) + 1  # data starts at row 2
        # Any range like Data_Validation!$<col>$<start>:$<col>$<end> -> fix the end row.
        desc_xml = re.sub(
            r'(Data_Validation!\$%s\$\d+:\$%s\$)\d+' % (col, col),
            lambda m: m.group(1) + str(end), desc_xml)
    return desc_xml


def patch_vocab(template_path, edits: dict) -> bytes:
    """Return new .xlsx bytes with `edits` (key -> list of values) applied.

    Columns not present in `edits` are preserved from the current workbook. Only the
    Data_Validation and Descriptions worksheet XML are changed; everything else is copied.
    """
    current = read_vocabularies(template_path)
    lists = {k: list(current.get(k, [])) for k in _KEY_TO_COL}
    for k, v in edits.items():
        if k in _KEY_TO_COL:
            lists[k] = [str(x).strip() for x in v if str(x).strip()]

    with zipfile.ZipFile(template_path, "r") as zin:
        dv_path = _find_sheet_path(zin, VOCAB_SHEET_NAME)
        desc_path = _find_sheet_path(zin, DESCRIPTIONS_SHEET_NAME)
        new_dv = _rebuild_sheetdata(zin.read(dv_path).decode("utf-8"), lists).encode("utf-8")
        new_desc = _resync_dropdowns(zin.read(desc_path).decode("utf-8"), lists).encode("utf-8")

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zout:
            for info in zin.infolist():
                if info.filename == dv_path:
                    data = new_dv
                elif info.filename == desc_path:
                    data = new_desc
                else:
                    data = zin.read(info.filename)
                zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                zi.compress_type = info.compress_type
                zi.external_attr = info.external_attr
                zi.internal_attr = info.internal_attr
                zi.create_system = info.create_system
                zout.writestr(zi, data)
    return buf.getvalue()


def verify_patched(xlsx_bytes: bytes, edits: dict) -> dict:
    """Confirm the patched workbook is structurally sound before it replaces the original."""
    facts = {"opens": False, "dropdowns_preserved": False, "vocab_matches": False}
    bio = io.BytesIO(xlsx_bytes)
    with zipfile.ZipFile(bio) as z:
        facts["opens"] = True
        desc_path = _find_sheet_path(z, DESCRIPTIONS_SHEET_NAME)
        facts["dropdowns_preserved"] = "<x14:dataValidations" in z.read(desc_path).decode("utf-8")
    vocab = read_vocabularies(io.BytesIO(xlsx_bytes))
    facts["vocab_matches"] = all(
        vocab.get(k) == [str(x).strip() for x in v if str(x).strip()]
        for k, v in edits.items() if k in _KEY_TO_COL
    )
    facts["ok"] = all(facts.values())
    return facts
