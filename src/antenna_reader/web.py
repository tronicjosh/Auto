"""Workflow-driven web app: pick a workflow -> upload -> view rows -> chat to refine
(with change highlighting + approve/revert + version history) -> download.

Run:  antenna-reader-web      (or: uvicorn antenna_reader.web:app)
Needs ANTHROPIC_API_KEY in the environment (or a .env file if python-dotenv is installed).
"""

import io
import json
import os
import socket
import uuid
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from .classify import classify_antenna
from .config import PROJECT_ROOT
from .conversation import Conversation
from .engine import apply_type_guardrails
from .extract import ExtractionError
from .store import SessionLog
from .workflows import diff_versions, get_workflow, list_workflows, reload_workflow

CONFIG_ROOT = PROJECT_ROOT / "workflow_configs"

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

app = FastAPI(title="Antenna Reader")

_TEMPLATES = Path(__file__).parent / "templates"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# In-memory session store (single-user local tool).
# session_id -> {workflow, conv, log, profile_key, classify_cost, versions, pending}
_SESSIONS: dict[str, dict] = {}
# Datasheets awaiting type confirmation between /classify and /extract.
# token -> {pdf_bytes, filename, workflow_id, manufacturer, model_name, source, classify_cost}
_PENDING: dict[str, dict] = {}


def _version(index, rows, flags, note, source, feedback=None) -> dict:
    return {"index": index, "rows": rows, "flags": flags, "note": note,
            "source": source, "feedback": feedback}


def _session_cost(sess) -> dict:
    """Cost shown to the user: the latest call + the session total (classify + every extract/refine)."""
    conv = sess["conv"]
    classify = sess.get("classify_cost")
    calls = ([classify] if classify else []) + conv.calls
    total = round(sum(c["cost_usd"] for c in calls), 6)
    return {"call": conv.last_call, "classify": classify, "session_total_usd": total,
            "n_calls": len(calls), "model": conv.model,
            "detected_type": sess.get("profile_label")}


def _guarded_flags(wf, rows, flags, profile_key):
    """Add the confirmed antenna-type's deterministic invariants on top of the base validation."""
    rails = wf.extras.get("type_guardrails", {}).get(profile_key or "", [])
    return apply_type_guardrails(rows, flags, rails) if rails else flags


def _require_session(session_id):
    sess = _SESSIONS.get(session_id)
    if not sess:
        raise HTTPException(404, "Session expired — please re-upload the datasheet.")
    return sess


@app.get("/")
def index():
    return HTMLResponse((_TEMPLATES / "index.html").read_text(encoding="utf-8"))


@app.get("/workflows")
def workflows():
    return JSONResponse({"workflows": [w.summary() for w in list_workflows()]})


@app.get("/workflows/{workflow_id}")
def workflow_definition(workflow_id: str):
    """The FULL definition of a workflow — so the whole architecture is visible in the UI:
    the AI instructions (prompt), output columns, edge-case rules, and on-screen text.
    All of it comes from the workflow_configs/<id>/ files, nothing hard-coded."""
    wf = get_workflow(workflow_id)
    if wf is None:
        raise HTTPException(404, f"Unknown workflow: {workflow_id!r}")
    source_options = []
    editable_vocab = {}
    try:
        vocab = wf.read_vocab(wf.template_path)
        source_options = vocab.get("source", [])
        editable_vocab = {k: vocab.get(k, [])
                          for k in ("source", "frequency", "type", "manufacturers")}
        prompt = wf.build_prompt(vocab)
    except Exception as exc:  # workbook unreadable etc. — still show the rest
        prompt = f"(could not render prompt: {exc})"
    # The editable base template (universal rules + [[PROFILE]] slot + [[...]] tags) vs the
    # rendered prompt actually sent. Per-type profiles are edited as files in profiles/.
    base_file = wf.extras.get("prompt_base_file", "prompt.txt")
    try:
        prompt_template = (CONFIG_ROOT / wf.id / base_file).read_text(encoding="utf-8")
    except Exception:
        prompt_template = ""
    return JSONResponse({
        "id": wf.id, "title": wf.title, "description": wf.description,
        "model": wf.model, "ui": wf.ui,
        "columns": wf.columns,
        "numeric_columns": sorted(wf.numeric_columns),
        "rules": wf.extras.get("rules", []),
        "config_sections": wf.extras.get("sections", []),
        "section_data": wf.extras.get("section_data", {}),
        "source_options": source_options,
        "vocab": editable_vocab,
        "prompt": prompt,
        "prompt_template": prompt_template,
        "config_dir": wf.extras.get("config_dir", ""),
    })


@app.post("/workflows/{workflow_id}")
def save_workflow_definition(workflow_id: str, payload: dict):
    """Write the edited config back to the workflow's files and reload it (live, no restart).
    Editable: title, description, on-screen text (ui), rules, bands, and the prompt template.
    The output columns and engine logic are fixed (the shared machinery), so they aren't edited here.
    """
    if get_workflow(workflow_id) is None:
        raise HTTPException(404, f"Unknown workflow: {workflow_id!r}")
    config_dir = CONFIG_ROOT / workflow_id
    meta_path = config_dir / "meta.json"
    if not meta_path.exists():
        raise HTTPException(404, "Workflow config not found.")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    for key in ("title", "description", "ui", "rules"):
        if payload.get(key) is not None:
            meta[key] = payload[key]
    if isinstance(payload.get("config_sections"), list):
        meta["config_sections"] = payload["config_sections"]
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    if isinstance(payload.get("prompt"), str):
        base_file = get_workflow(workflow_id).extras.get("prompt_base_file", "prompt.txt")
        (config_dir / base_file).write_text(payload["prompt"], encoding="utf-8")

    # Each declared section's rows go to <key>.json, coerced to the declared column types.
    section_data = payload.get("section_data") or {}
    for spec in meta.get("config_sections", []):
        key = spec.get("key")
        if not key:
            continue
        coltypes = {c["key"]: c.get("type", "text") for c in spec.get("columns", [])}
        clean = []
        for row in section_data.get(key, []):
            out = {}
            ok = True
            for ckey, ctype in coltypes.items():
                val = row.get(ckey, "")
                if ctype == "int":
                    try:
                        val = int(str(val).strip())
                    except (ValueError, TypeError):
                        ok = False
                        break
                else:
                    val = str(val).strip()
                out[ckey] = val
            if ok and any(str(v).strip() for v in out.values()):
                clean.append(out)
        (config_dir / f"{key}.json").write_text(json.dumps(clean, indent=2, ensure_ascii=False),
                                                encoding="utf-8")

    reload_workflow(workflow_id)
    return workflow_definition(workflow_id)


@app.post("/workflows/{workflow_id}/vocab")
def save_workflow_vocab(workflow_id: str, payload: dict):
    """Write edited controlled vocabularies back into the workbook's Data_Validation sheet.

    The workbook stays the single source of truth (its dropdowns are resynced to match), so
    the AI's choices always match the spreadsheet. SAFE BY DESIGN: the patched workbook is
    built in memory, structurally verified (opens, dropdowns intact, vocab re-reads), and the
    real template is replaced ONLY if every check passes — and a .bak is kept first.
    """
    import shutil

    from .vocab_writer import _KEY_TO_COL, patch_vocab, verify_patched

    wf = get_workflow(workflow_id)
    if wf is None:
        raise HTTPException(404, f"Unknown workflow: {workflow_id!r}")

    raw = payload.get("vocab") or {}
    edits = {k: [str(x).strip() for x in v if str(x).strip()]
             for k, v in raw.items() if k in _KEY_TO_COL and isinstance(v, list)}
    if not edits:
        raise HTTPException(400, "No editable vocabularies provided.")
    if any(not vals for vals in edits.values()):
        raise HTTPException(400, "A controlled vocabulary cannot be emptied.")

    template = wf.template_path
    try:
        patched = patch_vocab(template, edits)
        facts = verify_patched(patched, edits)
    except Exception as exc:
        raise HTTPException(500, f"Could not build the vocabulary update (workbook unchanged): {exc}")
    if not facts.get("ok"):
        raise HTTPException(500, f"Safety check failed — workbook left unchanged: {facts}")

    # Keep a backup, then atomically replace the template only after verification passed.
    shutil.copy2(template, str(template) + ".bak")
    tmp = str(template) + ".tmp"
    with open(tmp, "wb") as f:
        f.write(patched)
    os.replace(tmp, template)

    reload_workflow(workflow_id)
    return workflow_definition(workflow_id)


@app.post("/classify")
async def classify(pdf: UploadFile, workflow_id: str = Form("antenna"),
                   manufacturer: str = Form(""), model_name: str = Form(""),
                   source: str = Form("")):
    """Router pass: cheap model reads the datasheet and returns its antenna type, for the user
    to confirm before the (more expensive) extraction. Holds the PDF server-side under a token."""
    wf = get_workflow(workflow_id)
    if wf is None or not wf.enabled:
        raise HTTPException(400, f"Unknown workflow: {workflow_id!r}")
    pdf_bytes = await pdf.read()
    if not pdf_bytes:
        raise HTTPException(400, "Empty PDF upload.")
    profiles = wf.extras.get("profiles", [])
    router_prompt = wf.extras.get("router_prompt", "")
    if not (profiles and router_prompt):
        raise HTTPException(400, "This workflow has no router prompt / profiles configured.")

    try:
        result = classify_antenna(pdf_bytes, router_prompt, profiles,
                                  model=wf.extras.get("classify_model"))
    except ExtractionError as exc:
        raise HTTPException(502, str(exc))

    token = uuid.uuid4().hex
    _PENDING[token] = {"pdf_bytes": pdf_bytes, "filename": pdf.filename, "workflow_id": wf.id,
                       "manufacturer": manufacturer, "model_name": model_name, "source": source,
                       "classify_cost": result["cost"]}
    return JSONResponse({"token": token, "workflow_id": wf.id, "profiles": profiles,
                         "detected": {"key": result["key"], "label": result["label"],
                                      "reason": result["reason"]},
                         "cost": {"classify": result["cost"], "n_calls": 1,
                                  "session_total_usd": result["cost"]["cost_usd"]}})


@app.post("/extract")
async def extract(payload: dict):
    """Run the extraction for a classified datasheet, using the confirmed type's profile."""
    pend = _PENDING.get(payload.get("token"))
    if not pend:
        raise HTTPException(400, "Upload and classify the datasheet first.")
    wf = get_workflow(pend["workflow_id"])
    if wf is None or not wf.enabled:
        raise HTTPException(400, "Unknown workflow.")

    profile_key = payload.get("antenna_type")
    profile_label = next((p["label"] for p in wf.extras.get("profiles", [])
                          if p["key"] == profile_key), None)
    pdf_bytes, fname = pend["pdf_bytes"], pend["filename"]
    manufacturer, model_name, source = pend["manufacturer"], pend["model_name"], pend["source"]

    try:
        vocab = wf.read_vocab(wf.template_path)
        builder = lambda v, _pk=profile_key: wf.build_prompt(v, _pk)  # noqa: E731
        conv = Conversation(pdf_bytes, vocab, manufacturer=manufacturer,
                            model_name=model_name, model=wf.model, build_prompt=builder)
        data = conv.extract()
    except ExtractionError as exc:
        raise HTTPException(502, str(exc))

    rows, flags = wf.build_rows(data, vocab, conv.manufacturer, conv.model_name, source=source)
    flags = _guarded_flags(wf, rows, flags, profile_key)
    note = f"Extracted {len(rows)} row(s) from {fname} as {profile_label or 'antenna'}."
    v0 = _version(0, rows, flags, note, "extract")

    sid = uuid.uuid4().hex
    log = None
    try:
        log = SessionLog(sid, pdf_bytes, fname, manufacturer, model_name, conv.model)
        log.log_extraction(rows, flags, cost=conv.last_call)
    except Exception:
        log = None  # logging must never break extraction

    sess = {"workflow": wf, "conv": conv, "log": log, "source": source,
            "profile_key": profile_key, "profile_label": profile_label,
            "classify_cost": pend.get("classify_cost"), "versions": [v0], "pending": None}
    _SESSIONS[sid] = sess
    _PENDING.pop(payload.get("token"), None)
    return JSONResponse({"session_id": sid, "workflow_id": wf.id, "columns": wf.columns,
                         "rows": rows, "flags": flags, "note": v0["note"], "version_index": 0,
                         "detected_type": profile_label, "cost": _session_cost(sess)})


@app.post("/refine")
async def refine(payload: dict):
    sess = _require_session(payload.get("session_id"))
    feedback = (payload.get("message") or "").strip()
    if not feedback:
        raise HTTPException(400, "Empty message.")
    if sess["pending"] is not None:
        raise HTTPException(409, "Approve or revert the pending change first.")

    wf, conv = sess["workflow"], sess["conv"]
    try:
        data, note = conv.refine(feedback)
    except ExtractionError as exc:
        raise HTTPException(502, str(exc))

    rows, flags = wf.build_rows(data, conv.vocab, conv.manufacturer, conv.model_name,
                                source=sess.get("source", ""))
    flags = _guarded_flags(wf, rows, flags, sess.get("profile_key"))
    tip = sess["versions"][-1]
    diff = diff_versions(tip["rows"], rows, wf.columns, wf.diff_key_columns)
    pending = _version(len(sess["versions"]), rows, flags, note or "Updated.", "refine", feedback)
    pending["cost"] = conv.last_call  # the cost of this refine call, logged on approve
    sess["pending"] = pending

    return JSONResponse({"columns": wf.columns, "rows": rows, "flags": flags,
                         "note": pending["note"], "diff": diff, "pending": True,
                         "version_index": pending["index"], "cost": _session_cost(sess)})


@app.post("/approve")
async def approve(payload: dict):
    sess = _require_session(payload.get("session_id"))
    pending = sess["pending"]
    if pending is None:
        raise HTTPException(400, "No pending change to approve.")
    sess["versions"].append(pending)
    sess["pending"] = None
    if sess.get("log"):
        try:
            sess["log"].log_refine(pending["feedback"], pending["note"],
                                   pending["rows"], pending["flags"],
                                   cost=pending.get("cost"))
        except Exception:
            pass
    return JSONResponse({"version_index": pending["index"], "committed": True})


@app.post("/revert")
async def revert(payload: dict):
    sess = _require_session(payload.get("session_id"))
    if sess["pending"] is None:
        raise HTTPException(400, "No pending change to revert.")
    sess["pending"] = None
    sess["conv"].discard_last_turn()  # keep model context aligned with the screen
    wf, tip = sess["workflow"], sess["versions"][-1]
    return JSONResponse({"columns": wf.columns, "rows": tip["rows"], "flags": tip["flags"],
                         "note": tip["note"], "version_index": tip["index"], "pending": False})


@app.get("/version/{index}")
def version(index: int, session_id: str):
    sess = _require_session(session_id)
    versions = sess["versions"]
    if index < 0 or index >= len(versions):
        raise HTTPException(404, "No such version.")
    v, wf = versions[index], sess["workflow"]
    return JSONResponse({"columns": wf.columns, "rows": v["rows"], "flags": v["flags"],
                         "note": v["note"], "version_index": index, "source": v["source"],
                         "latest_index": len(versions) - 1})


@app.post("/download")
async def download(payload: dict):
    sess = _SESSIONS.get(payload.get("session_id"))
    if not sess:
        # allow a raw rows payload (used by tests/CLI), no workflow context
        rows = payload.get("rows")
        if not rows:
            raise HTTPException(400, "Nothing to download yet — extract a datasheet first.")
        from .workflows import get_workflow as _gw
        wf = _gw("antenna")
    else:
        wf = sess["workflow"]
        idx = payload.get("version")
        if idx is None:
            src = sess["pending"] or sess["versions"][-1]
        else:
            versions = sess["versions"]
            if idx < 0 or idx >= len(versions):
                raise HTTPException(404, "No such version.")
            src = versions[idx]
        rows = src["rows"]
        if sess.get("log"):
            try:
                sess["log"].log_download(rows)
            except Exception:
                pass

    buf = io.BytesIO()
    wf.write_output(wf.template_path, rows, buf)
    buf.seek(0)
    return StreamingResponse(buf, media_type=_XLSX, headers={
        "Content-Disposition": 'attachment; filename="antenna_batch.xlsx"',
    })


def run():
    import uvicorn
    host = "127.0.0.1"
    start = int(os.environ.get("ANTENNA_READER_PORT", "8000"))
    port = start
    for candidate in range(start, start + 25):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((host, candidate)) != 0:  # nothing listening here
                port = candidate
                break
    print(f"\n  Antenna Reader -> http://{host}:{port}\n", flush=True)
    uvicorn.run("antenna_reader.web:app", host=host, port=port)
