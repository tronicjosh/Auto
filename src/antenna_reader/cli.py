"""Command-line interface.

    antenna-reader extract <pdf|folder> [--out PATH] [--manufacturer X]
                           [--model-name Y] [--model claude-sonnet-4-6]
                           [--template PATH] [--dry-run]
    antenna-reader vocab   [--template PATH]
"""

import argparse
import sys
from pathlib import Path

from .config import DEFAULT_MODEL, TEMPLATE_PATH
from .extract import ExtractionError
from .pipeline import process_pdf
from .schema import COLUMNS
from .store import build_report
from .vocab import read_vocabularies


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv  # optional dependency
        load_dotenv()
    except Exception:
        pass


def _iter_pdfs(path: Path):
    if path.is_dir():
        return sorted(path.glob("*.pdf"))
    return [path]


def _print_report(result: dict) -> None:
    rows, flags = result["rows"], result["flags"]
    print(f"  {len(rows)} row(s) extracted")
    flagged = [(i, f) for i, f in enumerate(flags) if f]
    if flagged:
        print(f"  {len(flagged)} row(s) with validation flags:")
        for i, f in flagged:
            for col, msg in f.items():
                print(f"    row {i + 1} [{col}]: {msg}")
    else:
        print("  no validation flags")
    if result.get("out_path"):
        v = result["verify"]
        print(f"  wrote: {result['out_path']}")
        print(f"  dropdowns preserved: {v['has_dropdowns']} | "
              f"members match: {v['members_match']} | filled rows: {v['filled_rows']}")


def _print_rows_table(rows: list[dict]) -> None:
    print("\t".join(COLUMNS))
    for row in rows:
        print("\t".join(str(row.get(c, "")) for c in COLUMNS))


def _cmd_extract(args) -> int:
    template = Path(args.template)
    pdfs = _iter_pdfs(Path(args.pdf))
    if not pdfs:
        print(f"No PDF(s) found at {args.pdf}", file=sys.stderr)
        return 2

    multi = len(pdfs) > 1
    if multi and args.out:
        print("--out cannot be used with a folder of PDFs (one output per PDF).",
              file=sys.stderr)
        return 2

    failed = 0
    for pdf in pdfs:
        print(f"\n{pdf.name}")
        try:
            result = process_pdf(
                pdf,
                manufacturer=args.manufacturer,
                model_name=args.model_name,
                model=args.model,
                template=template,
                out_path=args.out,
                write=not args.dry_run,
            )
        except (ExtractionError, FileNotFoundError) as exc:
            print(f"  ERROR: {exc}", file=sys.stderr)
            failed += 1
            continue

        if args.dry_run:
            _print_rows_table(result["rows"])
        _print_report(result)

    return 1 if failed else 0


def _cmd_vocab(args) -> int:
    vocab = read_vocabularies(Path(args.template))
    for key, values in vocab.items():
        print(f"{key} ({len(values)}): {', '.join(values[:12])}"
              + (" ..." if len(values) > 12 else ""))
    return 0


def _cmd_corrections(args) -> int:
    print(build_report())
    return 0


def main(argv=None) -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(prog="antenna-reader",
                                     description="EMSS antenna datasheet -> IXUS batch Excel.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    ex = sub.add_parser("extract", help="extract a datasheet PDF (or folder) into the workbook")
    ex.add_argument("pdf", help="path to a PDF file or a folder of PDFs")
    ex.add_argument("--out", default=None, help="output xlsx path (single PDF only)")
    ex.add_argument("--manufacturer", default="", help="override manufacturer")
    ex.add_argument("--model-name", default="", help="override antenna model name")
    ex.add_argument("--model", default=DEFAULT_MODEL, help=f"Claude model (default {DEFAULT_MODEL})")
    ex.add_argument("--template", default=str(TEMPLATE_PATH), help="workbook template path")
    ex.add_argument("--dry-run", action="store_true", help="extract + validate, do not write")
    ex.set_defaults(func=_cmd_extract)

    vo = sub.add_parser("vocab", help="print the vocabularies read from the template")
    vo.add_argument("--template", default=str(TEMPLATE_PATH), help="workbook template path")
    vo.set_defaults(func=_cmd_vocab)

    co = sub.add_parser("corrections",
                        help="digest of logged web sessions: where the first pass fails + your fixes")
    co.set_defaults(func=_cmd_corrections)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
