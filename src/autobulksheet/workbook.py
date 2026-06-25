"""Write extracted rows into a COPY of the IXUS workbook's `Descriptions` sheet.

Why this is done by hand instead of with openpyxl: the Descriptions dropdowns are
Excel *x14 extension* data validations (in the sheet's <extLst>). openpyxl does not
model them and silently drops them — along with calcChain, connections, queryTables,
sharedStrings and table relationships — on save. Proven empirically.

So we treat the .xlsx as the zip it is: copy every member byte-for-byte EXCEPT the one
worksheet XML for `Descriptions`, into which we inject values while leaving the <extLst>
(the dropdowns) untouched. The template is only ever read, never mutated.
"""

import re
import zipfile
from xml.sax.saxutils import escape

from .config import DESCRIPTIONS_SHEET_NAME
from .schema import COLUMNS, NUMERIC_COLUMNS, column_letter

# Rows 2..30 in the antenna template are pre-styled empty slots. A workflow can override
# these (and the dropdown-range growth) via its output_spec; the defaults reproduce antenna.
FIRST_DATA_ROW = 2
LAST_TEMPLATE_ROW = 30
_DEFAULT_EXTEND = {
    "extend_columns": ["A", "B", "D"],   # simple cols whose dropdown range is "<c>2:<c>30"
    "extend_special": [                  # ranges that don't fit the simple pattern
        {"find": "E2:E21 E23 E25 E27", "template": "E2:E21 E23 E25 E27 E31:E{last}"},
    ],
}


# --------------------------------------------------------------------------- #
# Locating the target worksheet inside the zip (no hard-coded sheetN.xml)
# --------------------------------------------------------------------------- #

def _find_descriptions_sheet_path(zf: zipfile.ZipFile, sheet_name=DESCRIPTIONS_SHEET_NAME) -> str:
    """Resolve a sheet name -> its `xl/worksheets/sheetN.xml` member path."""
    wb_xml = zf.read("xl/workbook.xml").decode("utf-8")
    m = re.search(
        r'<sheet\b[^>]*\bname="%s"[^>]*\br:id="(rId\d+)"' % re.escape(sheet_name),
        wb_xml,
    ) or re.search(
        r'<sheet\b[^>]*\br:id="(rId\d+)"[^>]*\bname="%s"' % re.escape(sheet_name),
        wb_xml,
    )
    if not m:
        raise ValueError(f"Sheet {DESCRIPTIONS_SHEET_NAME!r} not found in workbook.xml")
    rid = m.group(1)

    rels = zf.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    m2 = re.search(r'<Relationship\b[^>]*\bId="%s"[^>]*\bTarget="([^"]+)"' % rid, rels) or \
        re.search(r'<Relationship\b[^>]*\bTarget="([^"]+)"[^>]*\bId="%s"' % rid, rels)
    if not m2:
        raise ValueError(f"Relationship {rid} not found in workbook rels")
    target = m2.group(1)
    if target.startswith("/"):
        return target.lstrip("/")
    return "xl/" + target  # targets in workbook.xml.rels are relative to xl/


# --------------------------------------------------------------------------- #
# Cell value rendering
# --------------------------------------------------------------------------- #

def _as_number(value):
    try:
        return float(str(value).strip())
    except (ValueError, AttributeError):
        return None


def _fmt_number(f: float) -> str:
    return str(int(f)) if f == int(f) else repr(f)


def _cell_xml(ref: str, style_attr: str, value, numeric: bool) -> str:
    """Build a <c> element, reusing the original style attribute (e.g. ' s="14"')."""
    if value is None or str(value).strip() == "":
        return f'<c r="{ref}"{style_attr}/>'
    if numeric:
        num = _as_number(value)
        if num is not None:
            return f'<c r="{ref}"{style_attr}><v>{_fmt_number(num)}</v></c>'
        # Not actually numeric — fall back to text so nothing is lost.
    text = escape(str(value))
    return f'<c r="{ref}"{style_attr} t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'


# --------------------------------------------------------------------------- #
# Sheet patching
# --------------------------------------------------------------------------- #

def _set_cell(xml: str, ref: str, value, numeric: bool) -> str:
    """Replace the self-closing empty cell at `ref` with a valued cell (style kept)."""
    if value is None or str(value).strip() == "":
        return xml  # leave the styled empty cell as-is
    pattern = re.compile(r'<c r="%s"([^>]*?)/>' % re.escape(ref))
    new_xml, n = pattern.subn(
        lambda m: _cell_xml(ref, m.group(1), value, numeric), xml, count=1
    )
    if n == 0:
        raise ValueError(f"Cell {ref} not found as an empty slot in the Descriptions sheet")
    return new_xml


def _row_cell_styles(xml: str, row_num: int) -> dict:
    """Map column letter -> style attribute string for an existing row's cells."""
    m = re.search(r'<row r="%d"[^>]*>(.*?)</row>' % row_num, xml)
    if not m:
        return {}
    styles = {}
    for col, attrs in re.findall(r'<c r="([A-R]+)%d"([^>]*?)/>' % row_num, m.group(1)):
        styles[col] = attrs
    return styles


def _build_row(row_num: int, row: dict, styles: dict, columns, numeric_columns) -> str:
    cells = []
    for pos, header in enumerate(columns, start=1):
        letter = column_letter(pos)
        ref = f"{letter}{row_num}"
        cells.append(_cell_xml(ref, styles.get(letter, ""), row.get(header, ""),
                               header in numeric_columns))
    return (f'<row r="{row_num}" spans="1:{len(columns)}" '
            f'x14ac:dyDescent="0.3">{"".join(cells)}</row>')


def _extend_validation(xml: str, last_row: int, columns, last_template_row, extend) -> str:
    """Grow the dimension and dropdown ranges to cover appended rows (> the styled slots)."""
    last_col = column_letter(len(columns))
    xml = xml.replace(f'<dimension ref="A1:{last_col}{last_template_row}"/>',
                      f'<dimension ref="A1:{last_col}{last_row}"/>')
    for col in extend.get("extend_columns", []):
        xml = xml.replace(
            f'<xm:sqref>{col}2:{col}{last_template_row}</xm:sqref>',
            f'<xm:sqref>{col}2:{col}{last_row}</xm:sqref>',
        )
    for sp in extend.get("extend_special", []):
        xml = xml.replace(f'<xm:sqref>{sp["find"]}</xm:sqref>',
                          f'<xm:sqref>{sp["template"].format(last=last_row)}</xm:sqref>')
    return xml


def _reset_descriptions_to_base(xml: str, columns, first_data_row, last_template_row, extend) -> str:
    """Return the Descriptions sheet reset to the empty-template state, so a workbook that ALREADY
    has antenna rows can be re-filled in place: values cleared (cell styles kept), any rows
    appended by a prior larger run dropped, and the dimension/dropdown ranges shrunk back to base.

    Everything else — the dropdowns (x14 validations), other sheets, formatting — is left exactly
    as-is. On an already-empty template every step matches nothing, so it is a no-op.
    """
    last_col = column_letter(len(columns))

    # 1. Drop rows appended beyond the styled template rows (from a previous larger run).
    xml = re.sub(r'<row r="(\d+)"[^>]*>.*?</row>',
                 lambda m: "" if int(m.group(1)) > last_template_row else m.group(0),
                 xml, flags=re.DOTALL)

    # 2. Clear values from the data cells (>= first_data_row), preserving each cell's style.
    def _clear(m):
        col, row, attrs = m.group(1), int(m.group(2)), m.group(3)
        if row < first_data_row:
            return m.group(0)  # header / above the data area
        sm = re.search(r'\s+s="\d+"', attrs)
        return f'<c r="{col}{row}"{sm.group(0) if sm else ""}/>'
    xml = re.sub(r'<c r="([A-R]+)(\d+)"([^>]*?)>(?:<v>.*?</v>|<is>.*?</is>)</c>',
                 _clear, xml, flags=re.DOTALL)

    # 3. Shrink the dimension + dropdown ranges back to base (inverse of _extend_validation).
    xml = re.sub(rf'<dimension ref="A1:{last_col}\d+"/>',
                 f'<dimension ref="A1:{last_col}{last_template_row}"/>', xml)
    for col in extend.get("extend_columns", []):
        xml = re.sub(rf'<xm:sqref>{col}2:{col}\d+</xm:sqref>',
                     f'<xm:sqref>{col}2:{col}{last_template_row}</xm:sqref>', xml)
    for sp in extend.get("extend_special", []):
        tmpl_re = re.escape(sp["template"]).replace(re.escape("{last}"), r"\d+")
        xml = re.sub(rf'<xm:sqref>{tmpl_re}</xm:sqref>',
                     f'<xm:sqref>{sp["find"]}</xm:sqref>', xml)
    return xml


def patch_descriptions_xml(sheet_xml: str, rows: list[dict], columns=COLUMNS,
                           numeric_columns=NUMERIC_COLUMNS, first_data_row=FIRST_DATA_ROW,
                           last_template_row=LAST_TEMPLATE_ROW, extend=None) -> str:
    """Inject `rows` into the target sheet XML; return the new XML string."""
    extend = extend or _DEFAULT_EXTEND
    n = len(rows)
    slots = last_template_row - first_data_row + 1

    # Fill the existing styled slots.
    for i, row in enumerate(rows[:slots]):
        rn = first_data_row + i
        for pos, header in enumerate(columns, start=1):
            ref = f"{column_letter(pos)}{rn}"
            sheet_xml = _set_cell(sheet_xml, ref, row.get(header, ""),
                                  header in numeric_columns)

    # Growth path: more rows than pre-styled slots -> append new rows + grow ranges.
    if n > slots:
        styles = _row_cell_styles(sheet_xml, last_template_row)
        extra = []
        start = last_template_row + 1
        for j, row in enumerate(rows[slots:]):
            extra.append(_build_row(start + j, row, styles, columns, numeric_columns))
        last_row = first_data_row + n - 1
        sheet_xml = sheet_xml.replace("</sheetData>", "".join(extra) + "</sheetData>", 1)
        sheet_xml = _extend_validation(sheet_xml, last_row, columns, last_template_row, extend)

    return sheet_xml


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def write_populated(template_path, rows: list[dict], out_path, *, columns=None,
                    numeric_columns=None, sheet_name=None, output_spec=None):
    """Write `rows` into the target sheet of the workbook, preserving everything else.

    `out_path` may be a filesystem path or a binary file-like object (e.g. BytesIO), and it may
    be the SAME file as `template_path` (update-in-place): the workbook is read fully into memory
    first, then the Descriptions sheet is reset to empty (clearing any existing antenna rows while
    keeping the dropdowns/structure) and re-filled. Every other zip member is preserved
    byte-for-byte. Column contract, sheet name, and range growth all come from config.
    """
    columns = columns or COLUMNS
    numeric_columns = NUMERIC_COLUMNS if numeric_columns is None else numeric_columns
    sheet_name = sheet_name or DESCRIPTIONS_SHEET_NAME
    spec = output_spec or {}
    first = spec.get("first_data_row", FIRST_DATA_ROW)
    last_tmpl = spec.get("last_template_row", LAST_TEMPLATE_ROW)
    extend = {"extend_columns": spec.get("extend_columns", _DEFAULT_EXTEND["extend_columns"]),
              "extend_special": spec.get("extend_special", _DEFAULT_EXTEND["extend_special"])}

    # Read every member into memory FIRST, so out_path may safely be the same file as
    # template_path — we never hold the input open while writing the output.
    with zipfile.ZipFile(template_path, "r") as zin:
        sheet_path = _find_descriptions_sheet_path(zin, sheet_name)
        members = [(info, zin.read(info.filename)) for info in zin.infolist()]

    base_xml = _reset_descriptions_to_base(
        next(d for i, d in members if i.filename == sheet_path).decode("utf-8"),
        columns, first, last_tmpl, extend)
    new_sheet = patch_descriptions_xml(base_xml, rows, columns, numeric_columns,
                                       first, last_tmpl, extend).encode("utf-8")

    with zipfile.ZipFile(out_path, "w") as zout:
        for info, data in members:
            if info.filename == sheet_path:
                data = new_sheet
            # Preserve member name, order, timestamp and compression.
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type = info.compress_type
            zi.external_attr = info.external_attr
            zi.internal_attr = info.internal_attr
            zi.create_system = info.create_system
            zout.writestr(zi, data)
    return out_path


def _count_filled_rows(sheet_xml: str) -> int:
    rows = {
        int(rn)
        for rn in re.findall(r'<c r="[A-Z]+(\d+)"[^>]*>(?:<is>|<v>)', sheet_xml)
        if int(rn) >= FIRST_DATA_ROW
    }
    return len(rows)


def verify_output(template_path, out_path, sheet_name=DESCRIPTIONS_SHEET_NAME) -> dict:
    """Cheap structural self-check (no Excel needed). Returns a dict of facts."""
    with zipfile.ZipFile(template_path) as zt, zipfile.ZipFile(out_path) as zo:
        template_members = set(zt.namelist())
        output_members = set(zo.namelist())
        sheet_path = _find_descriptions_sheet_path(zo, sheet_name)
        sheet_xml = zo.read(sheet_path).decode("utf-8")
    return {
        "members_match": template_members == output_members,
        "has_dropdowns": "<x14:dataValidations" in sheet_xml,
        "filled_rows": _count_filled_rows(sheet_xml),
        "sheet_path": sheet_path,
    }
