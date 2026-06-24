"""DatasheetSession — one datasheet's extraction + chat-refine + version history, with NO UI
or web dependency. A PyQt5 button, the FastAPI app, a CLI, or a test can all drive it.

This is the decoupled core that transfers into the production repo: it never imports GUI code,
so the dependency direction is always GUI -> session -> engine.
"""

from pathlib import Path

from . import settings
from .classify import classify_antenna
from .conversation import Conversation
from .engine import apply_type_guardrails
from .extract import ExtractionError
from .workflows import diff_versions


def find_datasheet(folder) -> Path:
    """Return the datasheet PDF inside a folder (the first .pdf). Raises if none."""
    pdfs = sorted(Path(folder).glob("*.pdf"))
    if not pdfs:
        raise ExtractionError(f"No PDF datasheet found in {folder}.")
    return pdfs[0]


def classify_datasheet(pdf_bytes, workflow, model=None, api_key=None) -> dict:
    """Router pass -> {key, label, reason, cost}. The detected type for the user to confirm.

    `model` overrides the workflow's configured classify model (else meta.json's classify_model).
    """
    return classify_antenna(pdf_bytes, workflow.extras.get("router_prompt", ""),
                            workflow.extras.get("profiles", []),
                            model=model or workflow.extras.get("classify_model"), api_key=api_key)


class DatasheetSession:
    """Holds the model conversation, the version list, and writes the batch sheet on demand."""

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
            pdf_bytes, self.vocab, manufacturer=manufacturer, model_name=model_name,
            model=model or workflow.model, api_key=api_key,
            build_prompt=lambda v, _pk=profile_key: workflow.build_prompt(v, _pk),
        )
        self.versions = []   # committed versions
        self.pending = None  # the un-approved refine, if any

    # --- internal ---
    def _build(self, data):
        rows, flags = self.workflow.build_rows(data, self.vocab, self.manufacturer,
                                               self.model_name, source=self.source)
        rails = self.workflow.extras.get("type_guardrails", {}).get(self.profile_key or "", [])
        if rails:
            flags = apply_type_guardrails(rows, flags, rails)
        return rows, flags

    @staticmethod
    def _version(index, rows, flags, note, kind, feedback=None):
        return {"index": index, "rows": rows, "flags": flags, "note": note,
                "kind": kind, "feedback": feedback}

    # --- flow ---
    def extract(self) -> dict:
        rows, flags = self._build(self.conv.extract())
        v0 = self._version(0, rows, flags,
                           f"Extracted {len(rows)} row(s) as {self.profile_label or 'antenna'}.",
                           "extract")
        self.versions = [v0]
        self.pending = None
        return v0

    def refine(self, feedback):
        """Returns (pending_version, diff). Does not commit until approve()."""
        if self.pending is not None:
            raise ExtractionError("Approve or revert the pending change first.")
        data, note = self.conv.refine(feedback)
        rows, flags = self._build(data)
        diff = diff_versions(self.versions[-1]["rows"], rows, self.workflow.columns,
                             self.workflow.diff_key_columns)
        self.pending = self._version(len(self.versions), rows, flags, note or "Updated.",
                                     "refine", feedback)
        return self.pending, diff

    def approve(self):
        if self.pending is None:
            return None
        self.versions.append(self.pending)
        v, self.pending = self.pending, None
        return v

    def revert(self):
        if self.pending is None:
            return None
        self.pending = None
        self.conv.discard_last_turn()  # keep the model's context aligned with the screen
        return self.versions[-1]

    def current(self):
        return self.pending or self.versions[-1]

    def current_rows(self):
        return self.current()["rows"]

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
