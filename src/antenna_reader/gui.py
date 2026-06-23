"""PyQt5 desktop GUI.

Pick a datasheet folder -> the tool classifies the antenna type (you confirm/correct it) ->
extracts -> writes the populated batch sheet IN PLACE at the configured path. Long-running
model calls run on a worker thread so the window never freezes.

Run:  python -m antenna_reader.gui     (needs ANTHROPIC_API_KEY in env / .env)

This GUI imports only the decoupled core (settings + session). The core never imports the GUI,
so the same logic drops into the production PyQt5 repo unchanged.
"""

import sys

from PyQt5 import QtCore, QtGui, QtWidgets

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from . import settings
from .session import DatasheetSession, classify_datasheet, find_datasheet
from .workflows import get_workflow

_FLAG_BG = QtGui.QColor(255, 226, 226)


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
        self.browse_btn = QtWidgets.QPushButton("Browse datasheet folder…")
        self.browse_btn.clicked.connect(self.on_browse)
        top.addWidget(self.browse_btn)
        self.path_lbl = QtWidgets.QLabel("(no datasheet selected)")
        top.addWidget(self.path_lbl, 1)
        top.addWidget(QtWidgets.QLabel("Type:"))
        self.type_combo = QtWidgets.QComboBox()
        for p in self.workflow.extras.get("profiles", []):
            self.type_combo.addItem(p["label"], p["key"])
        self.type_combo.setEnabled(False)
        top.addWidget(self.type_combo)
        self.extract_btn = QtWidgets.QPushButton("Confirm && Extract")
        self.extract_btn.setEnabled(False)
        self.extract_btn.clicked.connect(self.on_extract)
        top.addWidget(self.extract_btn)
        root.addLayout(top)

        self.detect_lbl = QtWidgets.QLabel("")
        self.detect_lbl.setStyleSheet("color:#178; font-size:12px;")
        self.detect_lbl.setWordWrap(True)
        root.addWidget(self.detect_lbl)

        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(len(self.workflow.columns))
        self.table.setHorizontalHeaderLabels(self.workflow.columns)
        root.addWidget(self.table, 1)

        bottom = QtWidgets.QHBoxLayout()
        self.status_lbl = QtWidgets.QLabel("Ready.")
        bottom.addWidget(self.status_lbl, 1)
        self.cost_lbl = QtWidgets.QLabel("")
        bottom.addWidget(self.cost_lbl)
        root.addLayout(bottom)

    def _refresh_config(self):
        s = settings.summary()
        extract = settings.extract_model_override() or self.workflow.model
        classify = settings.classify_model_override() or self.workflow.extras.get("classify_model")
        self.config_lbl.setText(
            f"Batch sheet: {s['batch_sheet']}    |    extract: {extract}    "
            f"classify: {classify}    |    API key: "
            + ("set" if s["api_key_set"] else "NOT SET"))
        if not s["api_key_set"]:
            self.browse_btn.setEnabled(False)
            self.status_lbl.setText("Set ANTHROPIC_API_KEY (environment or .env) to enable extraction.")

    # --- actions ---
    def on_browse(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select the datasheet folder", str(settings.datasheet_root()))
        if not folder:
            return
        try:
            self.pdf_path = find_datasheet(folder)
            self.pdf_bytes = self.pdf_path.read_bytes()
        except Exception as exc:
            self._error(str(exc))
            return
        self.path_lbl.setText(str(self.pdf_path))
        self.detect_lbl.setText("")
        self.table.setRowCount(0)
        self._busy("Identifying antenna type…")
        self._run(lambda: classify_datasheet(self.pdf_bytes, self.workflow,
                                             model=settings.classify_model_override()),
                  self._on_classified)

    def _on_classified(self, result):
        self.detected = result
        self.type_combo.setEnabled(True)
        idx = self.type_combo.findData(result.get("key"))
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        self.detect_lbl.setText(f"Detected: {result.get('label') or '?'} — {result.get('reason', '')}")
        c = result.get("cost") or {}
        self._idle(f"Type identified (classify ${c.get('cost_usd', 0):.4f}). "
                   f"Confirm or change the Type, then Extract.")

    def on_extract(self):
        if not self.pdf_bytes:
            return
        key, label = self.type_combo.currentData(), self.type_combo.currentText()
        self._busy(f"Extracting as {label} — this can take a moment…")

        def work():
            s = DatasheetSession(self.workflow, self.pdf_bytes, source="EMSS",
                                 profile_key=key, profile_label=label,
                                 classify_cost=(self.detected or {}).get("cost"),
                                 model=settings.extract_model_override())
            s.extract()
            path = s.write(settings.batch_sheet_path())
            return s, str(path)

        self._run(work, self._on_extracted)

    def _on_extracted(self, result):
        self.session, path = result
        cur = self.session.current()
        self._fill_table(cur["rows"], cur["flags"])
        cost = self.session.cost()
        self.cost_lbl.setText(f"cost ${cost['total_usd']:.4f} ({cost['n_calls']} calls)")
        self._idle(f"Wrote {len(cur['rows'])} row(s) to the batch sheet:  {path}")

    def _fill_table(self, rows, flags):
        cols = self.workflow.columns
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            row_flags = flags[r] if r < len(flags) else {}
            for c, col in enumerate(cols):
                item = QtWidgets.QTableWidgetItem(str(row.get(col, "")))
                msg = (row_flags or {}).get(col)
                if msg:
                    item.setBackground(_FLAG_BG)
                    item.setToolTip(msg)
                self.table.setItem(r, c, item)
        self.table.resizeColumnsToContents()

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

    def _idle(self, msg):
        self.status_lbl.setText(msg)
        self.browse_btn.setEnabled(True)
        self.extract_btn.setEnabled(self.detected is not None)

    def _error(self, msg):
        self.status_lbl.setText("Error: " + msg)
        self.browse_btn.setEnabled(True)
        self.extract_btn.setEnabled(self.detected is not None)


def run_gui():
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()   # keep a reference, or the window is GC'd and never shows
    win.show()
    win.raise_()
    win.activateWindow()
    sys.exit(app.exec_())


if __name__ == "__main__":
    run_gui()
