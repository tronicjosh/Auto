"""Paths and defaults. No secrets here — the API key comes from the environment."""

from pathlib import Path

# Default extraction model (configurable via the CLI --model flag).
DEFAULT_MODEL = "claude-sonnet-4-6"

# Default model for the cheap antenna-type classification pass (the router).
DEFAULT_CLASSIFY_MODEL = "claude-haiku-4-5"

# src/antenna_reader/config.py -> project root is two parents up from the package dir.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

TEMPLATE_PATH = PROJECT_ROOT / "data" / "template" / "IXUS_antenna_batch_processor2 1.xlsx"
OUTPUT_DIR = PROJECT_ROOT / "output"

# Sheet (inside the workbook) we populate. Resolved by name at write time, so the
# physical sheetN.xml path is discovered dynamically rather than hard-coded.
DESCRIPTIONS_SHEET_NAME = "Descriptions"
VOCAB_SHEET_NAME = "Data_Validation"

# Max tokens for the extraction response. Headroom for the model's reasoning preamble
# plus a full multi-band JSON on larger datasheets (still well under the streaming guard).
MAX_TOKENS = 16000
