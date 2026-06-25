"""DatasheetSession — one datasheet's extraction + write, with NO UI dependency. A PyQt5 button
or a test can drive it.

This is the decoupled core: it never imports GUI code, so the dependency direction is always
GUI -> session -> engine.
"""

from pathlib import Path

from . import settings
from .classify import classify_antenna
from .conversation import Conversation
from .engine import apply_type_guardrails


def classify_datasheet(pdf_bytes, workflow, model=None, api_key=None) -> dict:
    """Router pass -> {key, label, reason, cost}. The detected type for the user to confirm.

    `model` overrides the workflow's configured classify model (else meta.json's classify_model).
    """
    return classify_antenna(pdf_bytes, workflow.extras.get("router_prompt", ""),
                            workflow.extras.get("profiles", []),
                            model=model or workflow.extras.get("classify_model"), api_key=api_key)


class DatasheetSession:
    """Holds one datasheet's conversation + extracted rows, and writes the batch sheet on demand."""

    def __init__(self, workflow, pdf_bytes, *, manufacturer="", model_name="", source="",
                 profile_key=None, profile_label=None, classify_cost=None, model=None,
                 api_key=None):
        self.workflow = workflow
        self.pdf_bytes = pdf_bytes
        self.manufacturer = manufacturer
        self.model_name = model_name
        self.source = source
        self.profile_key = profile_key
        self.profile_label = profile_label
        self.classify_cost = classify_cost
        self.vocab = workflow.read_vocab(settings.template_path())
        self.conv = Conversation(
            pdf_bytes, self.vocab,
            lambda v, _pk=profile_key: workflow.build_prompt(v, _pk),
            model=model or workflow.model, api_key=api_key,
        )
        self.rows: list = []   # the extracted output rows
        self.flags: list = []  # one {column: message} flag dict per row ({} = clean)

    # --- internal ---
    def _build(self, data):
        rows, flags = self.workflow.build_rows(data, self.vocab, self.manufacturer,
                                               self.model_name, source=self.source)
        rails = self.workflow.extras.get("type_guardrails", {}).get(self.profile_key or "", [])
        if rails:
            flags = apply_type_guardrails(rows, flags, rails)
        return rows, flags

    # --- flow ---
    def extract(self) -> dict:
        """Run the extraction + deterministic engine; store and return the rows + flags."""
        self.rows, self.flags = self._build(self.conv.extract())
        return self.current()

    def current(self) -> dict:
        return {"rows": self.rows, "flags": self.flags}

    def current_rows(self) -> list:
        return self.rows

    @property
    def columns(self):
        return self.workflow.columns

    # --- output ---
    def write(self, path) -> Path:
        """Populate the batch sheet at `path` (dropdowns preserved) from the current rows."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.workflow.write_output(settings.template_path(), self.current_rows(), path)
        return path

    # --- cost ---
    def cost(self) -> dict:
        calls = ([self.classify_cost] if self.classify_cost else []) + self.conv.calls
        return {"classify": self.classify_cost, "calls": self.conv.calls,
                "total_usd": round(sum(c["cost_usd"] for c in calls), 6), "n_calls": len(calls)}
