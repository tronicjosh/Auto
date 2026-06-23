"""Read the controlled vocabularies live from the workbook's Data_Validation sheet.

Layout (1-based columns, data from row 2 down):
    A (1) = Antenna Manufacturer   (~290)
    C (3) = Frequency
    E (5) = Type
    G (7) = Version
    I (9) = Source                 (EMSS / NAD)

openpyxl is used in read-only mode; the workbook is never modified.
"""

from openpyxl import load_workbook

from .config import VOCAB_SHEET_NAME

# Antenna's default column map (1-based column -> vocab key). A workflow can override this
# entirely via its `vocab_spec` config, so this is just the fallback for direct/CLI callers.
_COLUMN_MAP = {
    1: "manufacturers",
    3: "frequency",
    5: "type",
    7: "version",
    9: "source",
}


def _col_to_int(col) -> int:
    """Accept a spreadsheet column as a 1-based number or a letter ('A'=1, 'C'=3, ...)."""
    if isinstance(col, int):
        return col
    s = str(col).strip()
    if s.isdigit():
        return int(s)
    n = 0
    for ch in s.upper():
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n


def read_vocabularies(template_path, column_map=None, sheet=None) -> dict:
    """Return controlled vocabularies as ordered, de-duped lists.

    `column_map` maps a column (number or letter) -> vocab key; defaults to the antenna
    layout. `sheet` is the worksheet to read; defaults to the configured vocab sheet. Both
    come from a workflow's `vocab_spec` so this same reader serves any workbook.
    """
    cmap = {_col_to_int(k): v for k, v in (column_map or _COLUMN_MAP).items()}
    sheet_name = sheet or VOCAB_SHEET_NAME
    wb = load_workbook(template_path, read_only=True, data_only=True)
    try:
        ws = wb[sheet_name]
        seen = {key: set() for key in cmap.values()}
        out = {key: [] for key in cmap.values()}
        for row in ws.iter_rows(min_row=2, values_only=True):
            for col, key in cmap.items():
                idx = col - 1
                value = row[idx] if idx < len(row) else None
                if value is None:
                    continue
                text = str(value).strip()
                if text and text not in seen[key]:
                    seen[key].add(text)
                    out[key].append(text)
        return out
    finally:
        wb.close()
