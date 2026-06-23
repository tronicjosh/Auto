"""End-to-end orchestration: PDF -> extract -> rows -> validate -> workbook."""

from pathlib import Path

from .config import DEFAULT_MODEL, OUTPUT_DIR, TEMPLATE_PATH
from .extract import extract_from_pdf
from .rows import sections_to_rows
from .validate import validate_rows
from .vocab import read_vocabularies
from .workbook import verify_output, write_populated


def build_rows(data: dict, vocab: dict, manufacturer: str = "", model_name: str = "",
               source: str = ""):
    """Expand + validate without any I/O (useful for tests and dry runs).

    `source` defaults to the first workbook source-vocabulary value when not supplied,
    so the 'Antenna Source' default lives in config, not a hard-coded constant.
    """
    if not source:
        options = vocab.get("source") or []
        source = options[0] if options else ""
    rows = sections_to_rows(data, manufacturer, model_name, source)
    flags = validate_rows(rows, vocab)
    return rows, flags


def process_pdf(pdf_path, *, manufacturer: str = "", model_name: str = "", source: str = "",
                model: str = DEFAULT_MODEL, template=TEMPLATE_PATH,
                out_path=None, api_key: str | None = None, write: bool = True) -> dict:
    """Run the full pipeline for one datasheet PDF.

    Returns a dict with: pdf, data, rows, flags, out_path, verify.
    Set write=False for a dry run (no workbook produced).
    """
    pdf_path = Path(pdf_path)
    vocab = read_vocabularies(template)
    data = extract_from_pdf(pdf_path.read_bytes(), vocab, model=model, api_key=api_key)
    rows, flags = build_rows(data, vocab, manufacturer, model_name, source)

    result = {"pdf": pdf_path, "data": data, "rows": rows, "flags": flags,
              "out_path": None, "verify": None}

    if write and rows:
        if out_path is None:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            out_path = OUTPUT_DIR / f"{pdf_path.stem}_populated.xlsx"
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_populated(template, rows, out_path)
        result["out_path"] = out_path
        result["verify"] = verify_output(template, out_path)

    return result
