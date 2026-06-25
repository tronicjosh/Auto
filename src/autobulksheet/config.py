"""Paths and defaults. No secrets here — the API key comes from the environment."""

from pathlib import Path

# Library fallback only — the antenna workflow sets its own model in meta.json ("model").
DEFAULT_MODEL = "claude-sonnet-4-6"

# Default model for the cheap antenna-type classification pass (the router).
DEFAULT_CLASSIFY_MODEL = "claude-haiku-4-5"

# src/autobulksheet/config.py -> project root is two parents up from the package dir.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# The source workbook (dropdowns/structure) is NOT bundled with the project — it is supplied at
# runtime via the IXUS_TEMPLATE environment variable (see settings.template_path()).

# Sheet (inside the workbook) we populate. Resolved by name at write time, so the
# physical sheetN.xml path is discovered dynamically rather than hard-coded.
DESCRIPTIONS_SHEET_NAME = "Descriptions"
VOCAB_SHEET_NAME = "Data_Validation"

# Max tokens for the extraction response. Headroom for the model's reasoning preamble
# plus a full multi-band JSON on larger datasheets (still well under the streaming guard).
MAX_TOKENS = 16000
