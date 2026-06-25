"""PyQt5 desktop GUI.

Pick a datasheet PDF -> the tool classifies the antenna type (you confirm/correct it) ->
extracts -> writes the populated batch sheet IN PLACE at the configured path. Long-running
model calls run on a worker thread so the window never freezes.

There is no in-app table: the result goes straight to the batch sheet, and you open that file
to review it.

Run:  python -m autobulksheet.gui     (needs ANTHROPIC_API_KEY in env / .env)

This GUI imports only the decoupled core (settings + session). The core never imports the GUI,
so the same logic drops into the production PyQt5 repo unchanged.
"""

import sys
from pathlib import Path

from PyQt5 import QtCore, QtGui, QtWidgets

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from . import settings
from .session import DatasheetSession, classify_datasheet
from .workflows import get_workflow


class _Task(QtCore.QThread):
    """Run one callable off the UI thread; emit its result or the error string."""

    done = QtCore.pyqtSignal(object)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            self.done.emit(self._fn())
        except Exception as exc:  # surfaced to the user, never crashes the UI
            self.failed.emit(str(exc))


class MainWindow(QtWidgets.QWidget):
    def __init__(self, workflow_id="antenna"):
        super().__init__()
        self.workflow = get_workflow(workflow_id)
        self.session = None
        self.pdf_bytes = None
        self.pdf_path = None
        self.written_path = None
        self.detected = None
        self._task = None
        self._build_ui()
        self._refresh_config()

    def _build_ui(self):
        self.setWindowTitle("IXUS — Antenna Datasheet to Batch Sheet")
        self.resize(1150, 720)
        root = QtWidgets.QVBoxLayout(self)

        self.config_lbl = QtWidgets.QLabel()
        self.config_lbl.setStyleSheet("color:#555;font-size:11px;")
        self.config_lbl.setWordWrap(True)
        root.addWidget(self.config_lbl)

        top = QtWidgets.QHBoxLayout()
        self.browse_btn = QtWidgets.QPushButton("Browse for datasheet (PDF)…")
        self.browse_btn.clicked.connect(self.on_browse)
        top.addWidget(self.browse_btn)
        self.path_lbl = QtWidgets.QLabel("(no datasheet selected)")
        top.addWidget(self.path_lbl, 1)
        top.addWidget(QtWidgets.QLabel("Type:"))
        self.type_combo = QtWidgets.QComboBox()
        # Only SUPPORTED types are selectable. Unsupported ones (e.g. Lens) stay in the config
        # and prompting for later, but are not offered here and are blocked on detection.
        self._unsupported = set()
        for p in self.workflow.extras.get("profiles", []):
            if p.get("supported", True):
                self.type_combo.addItem(p["label"], p["key"])
            else:
                self._unsupported.add(p["key"])
        self.type_combo.setEnabled(False)
        top.addWidget(self.type_combo)
        self.extract_btn = QtWidgets.QPushButton("Re-extract with type")
        self.extract_btn.setToolTip("If the detected type was wrong, pick the correct one "
                                    "and re-run the extraction.")
        self.extract_btn.setEnabled(False)
        self.extract_btn.clicked.connect(self.on_extract)
        top.addWidget(self.extract_btn)
        root.addLayout(top)

        self.detect_lbl = QtWidgets.QLabel("")
        self.detect_lbl.setStyleSheet("color:#178; font-size:12px;")
        self.detect_lbl.setWordWrap(True)
        root.addWidget(self.detect_lbl)

        # No in-app table — the result is written straight to the batch sheet, which the user
        # opens to review.
        self.result_lbl = QtWidgets.QLabel("")
        self.result_lbl.setWordWrap(True)
        self.result_lbl.setTextFormat(QtCore.Qt.RichText)
        self.result_lbl.setAlignment(QtCore.Qt.AlignTop)
        self.result_lbl.setStyleSheet("font-size:13px;")
        root.addWidget(self.result_lbl, 1)

        btn_row = QtWidgets.QHBoxLayout()
        self.open_btn = QtWidgets.QPushButton("Open batch sheet")
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self.on_open_sheet)
        btn_row.addWidget(self.open_btn)
        self.retry_btn = QtWidgets.QPushButton("Retry save")
        self.retry_btn.setToolTip("Re-save the last extraction to the batch sheet "
                                  "(no API cost). Use after closing the file in Excel.")
        self.retry_btn.setVisible(False)
        self.retry_btn.clicked.connect(self._save)
        btn_row.addWidget(self.retry_btn)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        bottom = QtWidgets.QHBoxLayout()
        self.status_lbl = QtWidgets.QLabel("Ready.")
        bottom.addWidget(self.status_lbl, 1)
        self.cost_lbl = QtWidgets.QLabel("")
        bottom.addWidget(self.cost_lbl)
        root.addLayout(bottom)

    def _refresh_config(self):
        s = settings.summary()
        extract = self.workflow.model
        classify = self.workflow.extras.get("classify_model")
        self.config_lbl.setText(
            f"Batch sheet: {s['batch_sheet']}    |    extract: {extract}    "
            f"classify: {classify}    |    API key: "
            + ("set" if s["api_key_set"] else "NOT SET"))
        if not s["api_key_set"]:
            self.browse_btn.setEnabled(False)
            self.status_lbl.setText("Set ANTHROPIC_API_KEY (environment or .env) to enable extraction.")

    # --- actions ---
    def on_browse(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select the antenna datasheet", str(settings.datasheet_root()),
            "PDF datasheets (*.pdf)")
        if not path:
            return
        try:
            self.pdf_path = Path(path)
            self.pdf_bytes = self.pdf_path.read_bytes()
        except Exception as exc:
            self._error(str(exc))
            return
        self.path_lbl.setText(str(self.pdf_path))
        self.detected = None
        self.session = None
        self.detect_lbl.setText("")
        self.result_lbl.setText("")
        self.open_btn.setEnabled(False)
        # Step 1 of 2: classify. _on_classified chains straight into step 2 (extract).
        self._busy("Step 1 of 2 — Identifying antenna type…")
        self._run(lambda: classify_datasheet(self.pdf_bytes, self.workflow),
                  self._on_classified)

    def _on_classified(self, result):
        self.detected = result
        c = result.get("cost") or {}

        # Unsupported type (e.g. a Matsing / lens antenna): do NOT extract — tell the user.
        if result.get("key") in self._unsupported:
            label = result.get("label") or "this"
            self.detect_lbl.setText(
                f"Detected type: <b>{label}</b> "
                f"(classify ${c.get('cost_usd', 0):.4f}) — {result.get('reason', '')}")
            self.result_lbl.setText(
                f"<span style='color:#b00;font-size:14px;'><b>This tool cannot process "
                f"{label} antennas yet.</b></span><br><br>"
                "Lens antennas (e.g. Matsing) are not supported in this version — too much of the "
                "data has to be read from the manufacturer datasheet by hand.<br><br>"
                "If this was misclassified, pick the correct type above and click "
                "“Re-extract with type”. Otherwise choose a different datasheet.")
            self.cost_lbl.setText(f"classify ${c.get('cost_usd', 0):.4f}")
            self.status_lbl.setText(f"Unsupported antenna type: {label}.")
            # Allow a manual override in case of misclassification, but nothing was extracted.
            self.browse_btn.setEnabled(True)
            self.type_combo.setEnabled(True)
            self.extract_btn.setEnabled(True)
            return

        idx = self.type_combo.findData(result.get("key"))
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)   # combo is still disabled during processing
        # If the router's answer didn't map to a supported type, fall back to the current
        # selection so extraction always runs with a valid profile.
        key, label = self.type_combo.currentData(), self.type_combo.currentText()
        shown = result.get("label") or f"{label} (uncertain)"
        self.detect_lbl.setText(
            f"Detected type: <b>{shown}</b> "
            f"(classify ${c.get('cost_usd', 0):.4f}) — {result.get('reason', '')}")
        # Auto-continue into extraction with the detected type — no manual confirm step.
        self._start_extract(key, label, step="Step 2 of 2 — ")

    def on_extract(self):
        """Manual re-run after the user corrects the Type dropdown."""
        if not self.pdf_bytes:
            return
        self._start_extract(self.type_combo.currentData(), self.type_combo.currentText(),
                            step="Re-extracting — ")

    def _start_extract(self, key, label, step=""):
        self._busy(f"{step}Extracting as {label} — this can take a moment…")

        def work():
            s = DatasheetSession(self.workflow, self.pdf_bytes, source="EMSS",
                                 profile_key=key, profile_label=label,
                                 classify_cost=(self.detected or {}).get("cost"))
            s.extract()
            return s            # extraction only — the (cheap, lock-prone) save is separate

        self._run(work, self._on_extracted)

    def _on_extracted(self, session):
        self.session = session   # keep it so a failed save can be retried without re-extracting
        self._save()

    def _save(self):
        """Write the current session to the batch sheet. A file-lock error is recoverable:
        the extraction stays in memory and the user can Retry save after closing Excel."""
        if self.session is None:
            return
        self._busy("Saving to the batch sheet…")
        try:
            self.written_path = str(self.session.write(settings.batch_sheet_path()))
        except (PermissionError, OSError) as exc:
            self._on_save_failed(exc)
            return
        self.retry_btn.setVisible(False)
        self._show_result()

    def _on_save_failed(self, exc):
        path = settings.batch_sheet_path()
        self.result_lbl.setText(
            "<span style='color:#b00;'><b>Could not save the batch sheet.</b></span><br>"
            f"<span style='color:#555;'>{path}</span><br><br>"
            "This usually means the file is <b>open in Excel</b>. Close it, then click "
            "<b>Retry save</b> — your extraction is kept, so retrying costs nothing.<br><br>"
            f"<span style='color:#888;'>Details: {exc}</span>")
        self.cost_lbl.setText("")
        self.open_btn.setEnabled(False)
        self.retry_btn.setVisible(True)
        self.retry_btn.setEnabled(True)
        self._idle("Save failed — close the file in Excel, then click “Retry save”.")

    def _show_result(self):
        cur = self.session.current()
        rows, flags = cur["rows"], cur["flags"]
        n_fields = sum(1 for rf in flags for v in (rf or {}).values() if v)
        n_rows_flagged = sum(1 for rf in flags if rf and any((rf or {}).values()))

        cost = self.session.cost()
        classify_usd = (cost.get("classify") or {}).get("cost_usd", 0.0)
        extract_usd = sum(c.get("cost_usd", 0.0) for c in cost.get("calls", []))
        self.cost_lbl.setText(f"total ${cost['total_usd']:.4f}")

        parts = [
            f"<b>✓ Wrote {len(rows)} row(s)</b> to the batch sheet:",
            f"<span style='color:#555;'>{self.written_path}</span>",
            "",
            "<b>Cost this run</b>",
            f"&nbsp;&nbsp;classify (router):&nbsp; ${classify_usd:.4f}",
            f"&nbsp;&nbsp;extract:&nbsp; ${extract_usd:.4f}",
            f"&nbsp;&nbsp;<b>total:&nbsp; ${cost['total_usd']:.4f}</b> "
            f"<span style='color:#888;'>({cost['n_calls']} API calls)</span>",
            "",
        ]
        if n_fields:
            parts.append(
                f"<span style='color:#b00;'>⚠ {n_fields} field(s) across {n_rows_flagged} "
                "row(s) were flagged as uncertain.</span> Open the batch sheet to review them.")
        else:
            parts.append("No fields were flagged — open the batch sheet to confirm.")
        self.result_lbl.setText("<br>".join(parts))
        self.open_btn.setEnabled(True)
        self._idle("Done — if the detected type is wrong, pick the correct one above and "
                   "click “Re-extract with type”.")

    def on_open_sheet(self):
        path = self.written_path or settings.batch_sheet_path()
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(path)))

    # --- task plumbing ---
    def _run(self, fn, on_done):
        self._task = _Task(fn)
        self._task.done.connect(on_done)
        self._task.failed.connect(self._error)
        self._task.start()

    def _busy(self, msg):
        self.status_lbl.setText(msg)
        self.browse_btn.setEnabled(False)
        self.extract_btn.setEnabled(False)
        self.type_combo.setEnabled(False)   # locked while classifying/extracting
        self.retry_btn.setVisible(False)

    def _set_idle(self, msg):
        self.status_lbl.setText(msg)
        self.browse_btn.setEnabled(True)
        # Type correction + re-extract unlock only after a first extraction has landed.
        ready = self.session is not None
        self.type_combo.setEnabled(ready)
        self.extract_btn.setEnabled(ready)

    def _idle(self, msg):
        self._set_idle(msg)

    def _error(self, msg):
        self._set_idle("Error: " + msg)


def run_gui():
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()   # keep a reference, or the window is GC'd and never shows
    win.show()
    win.raise_()
    win.activateWindow()
    sys.exit(app.exec_())


if __name__ == "__main__":
    run_gui()
