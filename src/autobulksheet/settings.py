"""Deployment configuration — read from the environment, never hardcoded.

Senior engineers configure the tool by setting these environment variables (a .env file is
loaded automatically if python-dotenv is installed). Nothing here contains a secret; the API
key lives only in the environment.

    ANTHROPIC_API_KEY     the Claude API key (required to run extraction)
    IXUS_BATCH_SHEET      full path to the batch-sheet .xlsx to populate IN PLACE (the output)
    IXUS_TEMPLATE         the source workbook (dropdowns/hidden sheets) extraction copies from
    IXUS_DATASHEET_ROOT   folder the "browse for datasheet" picker opens at (optional)

The extraction/classification MODELS are not configured here — they live in the config
(config/meta.json: "model" / "classify_model"), so the model travels with the prompts it was
tuned for.
"""

import os
from pathlib import Path

# Shown when a required path env var is unset, so the missing-file error is self-explanatory.
_BATCH_UNSET = "IXUS_BATCH_SHEET-is-not-set.xlsx"
_TEMPLATE_UNSET = "IXUS_TEMPLATE-is-not-set.xlsx"


def api_key() -> str:
    return os.environ.get("ANTHROPIC_API_KEY", "")


def has_api_key() -> bool:
    return bool(api_key())


def batch_sheet_path() -> Path:
    """The .xlsx the tool populates (the output), set via IXUS_BATCH_SHEET."""
    return Path(os.environ.get("IXUS_BATCH_SHEET", _BATCH_UNSET))


def template_path() -> Path:
    """The source workbook extraction copies dropdowns/structure from.

    Supplied at runtime via IXUS_TEMPLATE — there is no bundled template in the project.
    """
    return Path(os.environ.get("IXUS_TEMPLATE", _TEMPLATE_UNSET))


def datasheet_root() -> Path:
    """Where the 'browse for datasheet folder' dialog opens."""
    return Path(os.environ.get("IXUS_DATASHEET_ROOT", str(Path.home() / "Desktop")))


def summary() -> dict:
    """Non-secret view of the current configuration, for a startup banner / diagnostics."""
    return {
        "api_key_set": has_api_key(),
        "batch_sheet": str(batch_sheet_path()),
        "template": str(template_path()),
        "datasheet_root": str(datasheet_root()),
    }
