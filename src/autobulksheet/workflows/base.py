"""The Workflow object: the tool's config bundled with the function hooks that run it.

It holds the declarative config (columns, model, ui text) alongside callables into the engine
(vocab reading, row mapping, validation, the workbook writer). The loader builds it from the
`config/` files, so the behaviour is config-driven and this class itself stays generic.
"""

from dataclasses import dataclass, field
from typing import Callable

from ..engine import dot_decimals


@dataclass(frozen=True)
class Workflow:
    # --- identity ---
    id: str
    title: str
    description: str

    # --- generic config ---
    model: str
    output_sheet_name: str
    columns: list
    numeric_columns: frozenset

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
        """Turn the model's JSON into output rows + flags, routed through this workflow's hooks:
        map -> adjust (band-gain) -> dot-decimals -> validate.

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
        """Plain metadata view (no callables)."""
        return {"id": self.id, "title": self.title, "description": self.description,
                "enabled": self.enabled, "ui": self.ui}
