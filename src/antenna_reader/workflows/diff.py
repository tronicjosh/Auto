"""Pure cell-diff between two row-lists (no model calls).

Rows can be reordered, added, or removed between refinements, so rows are aligned by a
stable key (a few identifying columns); when the key is blank or collides, alignment
falls back to row index. Returns the changed cells and the added/removed row indices for
the frontend to highlight.
"""


def _key(row: dict, index: int, key_columns: list):
    parts = tuple((str(row.get(c, "") or "")).strip() for c in key_columns)
    return parts if any(parts) else ("__idx__", index)


def diff_versions(prev_rows: list, new_rows: list, columns: list, key_columns: list) -> dict:
    """Return {"changed": [{"row", "column"}], "added_rows": [...], "removed_rows": [...]}.

    `row` indices in `changed`/`added_rows` refer to positions in `new_rows`;
    `removed_rows` refers to positions in `prev_rows`.
    """
    prev_by_key = {}
    for i, r in enumerate(prev_rows):
        prev_by_key.setdefault(_key(r, i, key_columns), (i, r))

    changed = []
    added_rows = []
    matched_keys = set()

    for j, nr in enumerate(new_rows):
        k = _key(nr, j, key_columns)
        match = prev_by_key.get(k)
        if match is None:
            added_rows.append(j)
            continue
        matched_keys.add(k)
        _, pr = match
        for col in columns:
            if (str(nr.get(col, "") or "")) != (str(pr.get(col, "") or "")):
                changed.append({"row": j, "column": col})

    removed_rows = [i for k, (i, _) in prev_by_key.items() if k not in matched_keys]
    return {"changed": changed, "added_rows": added_rows, "removed_rows": sorted(removed_rows)}
