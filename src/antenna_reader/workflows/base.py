"""The Workflow abstraction.

A Workflow is a registry of *config + function hooks* that share one engine shape.
Generic data (columns, model, template, prompt builder) is declarative; the complex,
already-tested logic (vocab reading, row expansion, validation, workbook writing) is
referenced as callables on the proven modules. Adding a new workflow = a new instance,
not a rewrite of the app.
"""

from dataclasses import dataclass, field
from typing import Callable

from ..engine import dot_decimals


@dataclass(frozen=True)
class Workflow:
    # --- identity / landing-page framing ---
    id: str
    title: str
    description: str

    # --- generic config ---
    model: str
    output_sheet_name: str
    columns: list
    numeric_columns: frozenset
    diff_key_columns: list           # stable columns used to align rows for the diff

    # --- function hooks into the proven modules ---
    read_vocab: Callable             # (template_path) -> vocab dict
    build_prompt: Callable           # (vocab) -> str
    sections_to_rows: Callable       # (data, manufacturer, model_name) -> rows
    validate_rows: Callable          # (rows, vocab) -> flags
    write_output: Callable           # (template_path, rows, out)

    # Optional post-mapping adjustment (rows, data) -> rows, e.g. deterministic band-gain
    # selection from the model's raw transcription. Runs before validation.
    adjust_rows: Callable = None
    enabled: bool = True
    ui: dict = field(default_factory=dict)        # on-screen text/labels (from config)
    extras: dict = field(default_factory=dict)    # workflow-specific config (bands, rules, ...)

    def build_rows(self, data, vocab, manufacturer="", model_name="", source=""):
        """Mirror of pipeline.build_rows, routed through this workflow's hooks.

        `source` defaults to the first value of the workbook's source vocabulary when the
        caller doesn't supply one — so the default is config, not a hard-coded constant.
        """
        if not source:
            options = vocab.get("source") or []
            source = options[0] if options else ""
        rows = self.sections_to_rows(data, manufacturer, model_name, source)
        if self.adjust_rows is not None:
            rows = self.adjust_rows(rows, data)
        dot_decimals(rows, self.numeric_columns)   # decimals use '.', never ',' (numeric cells)
        flags = self.validate_rows(rows, vocab)
        return rows, flags

    def summary(self) -> dict:
        """Metadata for the landing page (no callables)."""
        return {"id": self.id, "title": self.title, "description": self.description,
                "enabled": self.enabled, "ui": self.ui}
