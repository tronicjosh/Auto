"""Deployment configuration — read from the environment, never hardcoded.

Senior engineers configure the tool by setting these environment variables (a .env file is
loaded automatically if python-dotenv is installed). Nothing here contains a secret; the API
key lives only in the environment.

    ANTHROPIC_API_KEY     the Claude API key (required to run extraction)
    IXUS_BATCH_SHEET      full path to the batch-sheet .xlsx to populate IN PLACE
                          (prod: C:\\alphawave\\...\\IXUS_antenna_batch_processor.xlsx)
    IXUS_TEMPLATE         the source workbook (dropdowns/hidden sheets) extraction copies from
    IXUS_DATASHEET_ROOT   folder the "browse for datasheet folder" picker opens at
    IXUS_EXTRACT_MODEL    override the extraction model (default from config.py)
    IXUS_CLASSIFY_MODEL   override the router/classification model
"""

import os
from pathlib import Path

from .config import TEMPLATE_PATH

# Dev default while running locally in the vscode project; in production this is the env var.
_DEV_BATCH_SHEET = Path.home() / "Desktop" / "CAD" / "IXUS_antenna_batch.xlsx"


def api_key() -> str:
    return os.environ.get("ANTHROPIC_API_KEY", "")


def has_api_key() -> bool:
    return bool(api_key())


def batch_sheet_path() -> Path:
    """The .xlsx that gets populated in place (overwritten on every change)."""
    return Path(os.environ.get("IXUS_BATCH_SHEET", str(_DEV_BATCH_SHEET)))


def template_path() -> Path:
    """The source workbook extraction copies dropdowns/structure from."""
    return Path(os.environ.get("IXUS_TEMPLATE", str(TEMPLATE_PATH)))


def datasheet_root() -> Path:
    """Where the 'browse for datasheet folder' dialog opens."""
    return Path(os.environ.get("IXUS_DATASHEET_ROOT", str(Path.home() / "Desktop")))


def extract_model_override() -> str | None:
    """Optional env override; None means 'use the workflow's configured model' (meta.json)."""
    return os.environ.get("IXUS_EXTRACT_MODEL") or None


def classify_model_override() -> str | None:
    return os.environ.get("IXUS_CLASSIFY_MODEL") or None


def summary() -> dict:
    """Non-secret view of the current configuration, for a startup banner / diagnostics."""
    return {
        "api_key_set": has_api_key(),
        "batch_sheet": str(batch_sheet_path()),
        "template": str(template_path()),
        "datasheet_root": str(datasheet_root()),
        "extract_model_override": extract_model_override(),
        "classify_model_override": classify_model_override(),
    }
