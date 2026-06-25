#!/usr/bin/env python3
"""Launcher for the IXUS antenna datasheet -> batch sheet tool.

Run this to open the desktop GUI:

    python run.py

It loads configuration from a local `.env` (if present), checks that the required settings are
in place, prints a short summary, then opens the GUI. All configuration is via environment
variables (see `.env.example`):

    ANTHROPIC_API_KEY   (required)  your Claude API key
    IXUS_BATCH_SHEET    the .xlsx the tool populates in place
    IXUS_TEMPLATE       the empty source workbook to copy the dropdowns from (required)

The models are set in the config (config/meta.json), not here.

This is only a thin entry point — it adds no behaviour of its own and imports the same package
the GUI uses, so it stays correct as the tool evolves.
"""

import sys
from pathlib import Path

# Make the bundled package importable when run straight from the project folder (src layout),
# so this works whether or not the package has been pip-installed.
_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Load .env (KEY=value lines) into the environment BEFORE anything reads settings.
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def main() -> int:
    from autobulksheet import settings
    from autobulksheet.workflows import get_workflow

    wf = get_workflow("antenna")
    template = settings.template_path()

    print("IXUS antenna datasheet -> batch sheet")
    print(f"  API key:        {'set' if settings.has_api_key() else 'NOT SET'}")
    print(f"  Batch sheet:    {settings.batch_sheet_path()}")
    print(f"  Template:       {template}")
    print(f"  Extract model:  {wf.model}")
    print(f"  Classify model: {wf.extras.get('classify_model')}")

    if not settings.has_api_key():
        print()
        print("ERROR: ANTHROPIC_API_KEY is not set.")
        print("Set it in your environment, or in a .env file next to this script:")
        print("    ANTHROPIC_API_KEY=sk-ant-...")
        print("See .env.example for all available settings.")
        return 1

    if not template.exists():
        print()
        print(f"WARNING: template workbook not found at {template}")
        print("         Set IXUS_TEMPLATE to the IXUS batch workbook (the dropdown source).")

    try:
        from autobulksheet.gui import run_gui
    except ImportError as exc:
        print()
        print(f"ERROR: could not load the GUI ({exc}).")
        print("Install the GUI dependency:  pip install PyQt5")
        return 1

    run_gui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
