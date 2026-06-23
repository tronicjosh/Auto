"""Persist web sessions (datasheet + the correction conversation) so recurring
model mistakes can be reviewed and distilled into prompt rules by hand.

Each session becomes a self-contained folder under `conversations/`:
    <timestamp>__<pdf-stem>__<sid8>/
        datasheet.pdf     the exact PDF (reusable later as a test fixture / example)
        record.json       the full conversation: initial extraction + each correction

Nothing here calls the model — it only records what happened. `build_report()`
aggregates the logs into a human-readable digest of the corrections you've had to
make and where the first-pass extraction fails most often.
"""

import datetime
import hashlib
import json
from collections import Counter
from pathlib import Path

from .config import PROJECT_ROOT

LOG_DIR = PROJECT_ROOT / "conversations"


def _n_flagged(flags) -> int:
    return sum(1 for f in (flags or []) if f)


def _flag_summary(flags) -> dict:
    c = Counter()
    for f in flags or []:
        for col in f:
            c[col] += 1
    return dict(c)


def _last_rowcount(record) -> int:
    for turn in reversed(record["turns"]):
        if turn["kind"] == "extract":
            return turn["rows"]
        if turn["kind"] == "refine":
            return turn["rows_after"]
    return 0


class SessionLog:
    """Append-only log for one web session; re-saved to disk after each event."""

    def __init__(self, session_id, pdf_bytes, pdf_filename, manufacturer, model_name,
                 model, base_dir=LOG_DIR):
        stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
        stem = Path(pdf_filename or "datasheet").stem[:40] or "datasheet"
        self.dir = Path(base_dir) / f"{stamp}__{stem}__{session_id[:8]}"
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "datasheet.pdf").write_bytes(pdf_bytes)
        self.record = {
            "session_id": session_id,
            "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "model": model,
            "pdf": {
                "filename": pdf_filename,
                "sha256": hashlib.sha256(pdf_bytes).hexdigest(),
                "bytes": len(pdf_bytes),
            },
            "manufacturer_override": manufacturer,
            "model_override": model_name,
            "turns": [],
            "accepted": False,
            "final_rows": None,
        }
        self._save()

    def _save(self):
        (self.dir / "record.json").write_text(
            json.dumps(self.record, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def log_extraction(self, rows, flags, cost=None):
        self.record["turns"].append({
            "kind": "extract",
            "rows": len(rows),
            "flagged_rows": _n_flagged(flags),
            "flag_summary": _flag_summary(flags),
            "rows_data": rows,
            "flags": flags,
            "cost": cost,
        })
        self.record["total_cost_usd"] = self._total_cost()
        self._save()

    def log_refine(self, feedback, note, rows, flags, cost=None):
        self.record["turns"].append({
            "kind": "refine",
            "feedback": feedback,
            "model_note": note,
            "rows_before": _last_rowcount(self.record),
            "rows_after": len(rows),
            "flagged_rows": _n_flagged(flags),
            "flag_summary": _flag_summary(flags),
            "rows_data": rows,
            "flags": flags,
            "cost": cost,
        })
        self.record["total_cost_usd"] = self._total_cost()
        self._save()

    def _total_cost(self) -> float:
        total = 0.0
        for turn in self.record["turns"]:
            cost = turn.get("cost")
            if cost:
                total += cost.get("cost_usd", 0.0)
        return round(total, 6)

    def log_download(self, rows):
        self.record["accepted"] = True
        self.record["final_rows"] = rows
        self._save()


def load_records(base_dir=LOG_DIR):
    """Return [(folder, record_dict), ...] sorted oldest-first."""
    base = Path(base_dir)
    if not base.exists():
        return []
    out = []
    for rj in sorted(base.glob("*/record.json")):
        try:
            out.append((rj.parent, json.loads(rj.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def build_report(base_dir=LOG_DIR) -> str:
    """A human-readable digest: per-session corrections + where it fails most."""
    records = load_records(base_dir)
    if not records:
        return "No logged sessions yet. Use the web app, then re-run this."

    lines = [f"{len(records)} logged session(s)\n"]
    all_feedback = []
    initial_flags = Counter()

    for folder, rec in records:
        pdf = rec.get("pdf", {}).get("filename", "?")
        turns = rec.get("turns", [])
        extract = next((t for t in turns if t["kind"] == "extract"), None)
        refines = [t for t in turns if t["kind"] == "refine"]

        lines.append(f"- {pdf}  ({folder.name})")
        if extract:
            lines.append(f"    initial: {extract['rows']} rows, "
                         f"{extract['flagged_rows']} flagged  {extract.get('flag_summary', {})}")
            for col, n in extract.get("flag_summary", {}).items():
                initial_flags[col] += n
        for t in refines:
            all_feedback.append(t["feedback"])
            lines.append(f'    fix: "{t["feedback"]}"')
            lines.append(f"       -> {t.get('model_note', '')}  "
                         f"[{t['rows_before']} -> {t['rows_after']} rows, {t['flagged_rows']} flagged]")
        lines.append(f"    accepted/downloaded: {rec.get('accepted')}\n")

    lines.append("=== where the first pass fails most (initial-extraction flags, all sessions) ===")
    for col, n in initial_flags.most_common():
        lines.append(f"  {n:4d}  {col}")

    lines.append("\n=== every correction you've made (candidate prompt rules) ===")
    for fb in all_feedback:
        lines.append(f"  - {fb}")

    return "\n".join(lines)
