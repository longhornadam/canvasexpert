"""FeedbackExpert routes — the pseudonymized scoring/feedback pipeline.

Phase B: assignment-driven guided flow (SSE), persona library, feedback patterns.
Phase A (manual CSV-drop) preserved as secondary lane for NQ + own-tool users.
"""
import glob
import json
import os
from datetime import datetime

import requests
from fastapi import APIRouter, Form, Query
from fastapi.responses import JSONResponse, StreamingResponse

import feedback_pipeline as fp
import feedback_safety as safety
import feedback_scrub
import feedback_vault
import openrouter_client as orc
from .. import config, workspace
from ..canvas_client import _canvas_get, _canvas_get_all, _canvas_headers, _canvas_send
from ..deps import _sse, list_rubric_files

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


def _vault():
    return feedback_vault.Vault(os.path.join(workspace.feedback_folder("_vault"), "vault.json"))


def _ai_ta_name():
    return config.get_ai_ta_persona().get("name") or "your AI teaching assistant"


def _run(gen):
    """Drain a pipeline generator into (log, folder)."""
    log, folder = [], None
    for line in gen:
        if line.startswith("FOLDER: "):
            folder = line[len("FOLDER: "):]
        else:
            log.append(line)
    return log, folder


def _load_rubric_text(rubric_name):
    if not rubric_name:
        return ""
    for r in list_rubric_files():
        if r["label"] == rubric_name or os.path.basename(r["path"]) == rubric_name:
            try:
                with open(r["path"], encoding="utf-8") as f:
                    return f.read()
            except Exception:
                return ""
    return ""


def _audit(entry: dict):
    """Append a content-free provenance line to _audit/audit.log (pseudonymous only)."""
    path = os.path.join(workspace.feedback_folder("_audit") or ".", "audit.log")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        entry = {"ts": datetime.now().isoformat(timespec="seconds"), **entry}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def _bundle_paths():
    forllm = workspace.feedback_folder("2_ForLLM")
    if not forllm or not os.path.isdir(forllm):
        return []
    return sorted(glob.glob(os.path.join(forllm, "*__bundle.json")))


# ======================================================================
# Phase A — preserved CSV-drop-folder workflow (New Quizzes + own tool)
# ======================================================================

@router.post("/persona")
def save_persona(name: str = Form(""), personality: str = Form("")):
    config.set_ai_ta_persona(name, personality)
    return JSONResponse({"ok": True})


@router.post("/process-inbox")
def process_inbox():
    if not workspace.feedback_root():
        return JSONResponse({"ok": False, "error": "No workspace configured — finish setup first."})
    workspace.ensure_workspace()
    log, folder = _run(fp.process_inbox(
        workspace.feedback_folder("1_Inbox"),
        workspace.feedback_folder("2_ForLLM"),
        workspace.feedback_folder("_archive"),
        _vault(), _ai_ta_name()))
    return JSONResponse({"ok": True, "folder": folder or workspace.feedback_folder("2_ForLLM"),
                         "log": log})


@router.post("/reidentify")
def reidentify():
    if not workspace.feedback_root():
        return JSONResponse({"ok": False, "error": "No workspace configured — finish setup first."})
    workspace.ensure_workspace()
    log, folder = _run(fp.reidentify_dir(
        workspace.feedback_folder("3_FromLLM"),
        workspace.feedback_folder("4_ToEnter"),
        _vault()))
    return JSONResponse({"ok": True, "folder": folder or workspace.feedback_folder("4_ToEnter"),
                         "log": log})


@router.post("/openrouter-config")
def openrouter_config(api_key: str = Form(""), model: str = Form("")):
    if api_key.strip():
        config.set_openrouter_key(api_key.strip())
    if model.strip():
        config.set_openrouter_model(model.strip())
    return JSONResponse({"ok": True, "has_key": config.has_openrouter_key(),
                         "model": config.get_openrouter_model()})


@router.get("/status")
def status():
    """Drives the UI: key/model presence, available rubrics, and per-bundle red/green
    safety verdicts + token estimates for the ForLLM folder."""
    fb = workspace.feedback_root()
    bundles = []
    if fb:
        vault = _vault()
        for path in _bundle_paths():
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            verdict = safety.scan_payload(data, vault)
            bundles.append({
                "name": os.path.basename(path),
                "green": verdict["green"],
                "hard": len(verdict["hard"]),
                "soft": len(verdict["soft"]),
                "soft_names": sorted({s["name"] for s in verdict["soft"]}),
                "tokens": orc.estimate_tokens(data),
            })
    return JSONResponse({
        "configured":  bool(fb),
        "has_key":     config.has_openrouter_key(),
        "model":       config.get_openrouter_model(),
        "rubrics":     [r["label"] for r in list_rubric_files()],
        "bundles":     bundles,
    })


@router.post("/score-openrouter")
def score_openrouter(rubric_name: str = Form(""), bundle_name: str = Form("")):
    """Send pseudonymized bundles to OpenRouter, re-identify results to ToEnter.
    HARD-GATED: a bundle that fails the safety scan is NEVER sent (defense in depth —
    the UI also disables the button, but the server refuses regardless)."""
    if not workspace.feedback_root():
        return JSONResponse({"ok": False, "error": "No workspace configured."})
    if not config.has_openrouter_key():
        return JSONResponse({"ok": False, "error": "No OpenRouter API key saved."})

    vault, persona = _vault(), config.get_ai_ta_persona()
    model, api_key = config.get_openrouter_model(), config.get_openrouter_key()
    rubric_text = _load_rubric_text(rubric_name)
    toenter = workspace.feedback_folder("4_ToEnter")
    os.makedirs(toenter, exist_ok=True)

    paths = _bundle_paths()
    if bundle_name:
        paths = [p for p in paths if os.path.basename(p) == bundle_name]
    if not paths:
        return JSONResponse({"ok": False, "error": "No bundles to score."})

    log = []
    for path in paths:
        name = os.path.basename(path)
        with open(path, encoding="utf-8") as f:
            bundle = json.load(f)
        verdict = safety.scan_payload(bundle, vault)
        if not verdict["green"]:
            log.append(f"⛔ {name}: BLOCKED — not pseudonymized ({verdict['hard'][:1]}). Not sent.")
            _audit({"action": "blocked", "bundle": name, "hard": len(verdict["hard"])})
            continue
        try:
            results = orc.score(bundle, rubric_text, persona, api_key=api_key, model=model)
        except Exception as e:
            log.append(f"!! {name}: OpenRouter error — {e}")
            continue
        rows = fp.reidentify(results, vault)
        stem = os.path.splitext(name)[0]
        dest = os.path.join(toenter, f"{stem}__to-enter.csv")
        with open(dest, "w", encoding="utf-8", newline="") as f:
            f.write(fp.reidentified_csv(rows))
        _audit({"action": "scored", "bundle": name, "model": model,
                "responses": len(rows), "tokens_est": orc.estimate_tokens(bundle)})
        log.append(f"✓ {name}: scored {len(rows)} response(s) → ToEnter (review before posting)")

    return JSONResponse({"ok": True, "folder": toenter, "log": log})


# ======================================================================
# Phase B — Persona library endpoints
# ======================================================================

@router.get("/personas")
def list_personas():
    """Return all personas (built-in + custom)."""
    return JSONResponse({"personas": config.list_personas()})


@router.post("/personas/custom")
def add_custom_persona(persona_id: str = Form(""), name: str = Form(""),
                       personality: str = Form("")):
    config.save_custom_persona(persona_id.strip(), name.strip(), personality.strip())
    return JSONResponse({"ok": True, "personas": config.list_personas()})


@router.delete("/personas/custom")
def delete_custom_persona(persona_id: str = Form("")):
    config.remove_custom_persona(persona_id.strip())
    return JSONResponse({"ok": True, "personas": config.list_personas()})


# ======================================================================
# Phase B — Feedback Pattern endpoints
# ======================================================================

@router.get("/patterns")
def list_patterns():
    return JSONResponse({"patterns": config.list_feedback_patterns()})


@router.post("/patterns")
def save_patterns(patterns: str = Form()):
    """Replace all feedback patterns with the provided JSON list."""
    try:
        parsed = json.loads(patterns)
        if not isinstance(parsed, list):
            return JSONResponse({"ok": False, "error": "Must be a JSON array."})
        config.set_feedback_patterns(parsed)
        return JSONResponse({"ok": True, "patterns": config.list_feedback_patterns()})
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": str(e)})


# ======================================================================
# Phase B — Assignment-driven guided flow
#
# Two steps, so the paid OpenRouter call is gated on an explicit cost
# confirmation (an SSE stream can't pause mid-flight for a client OK):
#   1. /run/prepare (JSON): fetch → pseudonymize → HARD safety gate →
#      write pseudonymized bundle → return token estimate. Nothing paid yet.
#   2. /run/stream  (SSE): only after the teacher confirms the cost — load
#      the prepared bundle, re-scan (defense in depth), score, re-identify.
# ======================================================================

# Plain-text code/text files we can fold into the scored response. (HTML files are
# included raw — see pseudonymize_submissions — so their tags survive scoring.)
_CODE_EXTS = {".py", ".html", ".htm", ".css", ".js", ".txt", ".md", ".json", ".csv"}
_MAX_CODE_BYTES = 256 * 1024


def _enrich_with_code_files(subs):
    """For each submission, download plain-text code-file attachments into
    s['code_files'] = [{filename, text}]. Non-text attachments (image/PDF/DOCX) are
    left untouched (still surfaced as attachment-only). Best-effort: any fetch
    failure or oversized/binary file is skipped, never fatal. Student file content
    is PII — it stays local (scrubbed into SAFE, raw into PRIVATE), never logged."""
    hdrs, _ = _canvas_headers()
    if not hdrs:
        return
    sess = requests.Session()
    sess.headers.update(hdrs)
    for s in subs:
        files = []
        for att in (s.get("attachments") or []):
            fn = att.get("filename") or att.get("display_name") or ""
            if os.path.splitext(fn)[1].lower() not in _CODE_EXTS:
                continue
            if (att.get("size") or 0) > _MAX_CODE_BYTES:
                continue
            url = att.get("url")
            if not url:
                continue
            try:
                r = sess.get(url, timeout=30)
            except requests.RequestException:
                continue
            if r.status_code == 200 and len(r.content) <= _MAX_CODE_BYTES:
                files.append({"filename": fn, "text": r.text})
        if files:
            s["code_files"] = files


def _fetch_submissions(course_id: str, assignment_id: str):
    """Fetch one assignment's submissions (with user, for vault names). Narrowed
    server-side by assignment_ids[] so we don't pull the whole course. Returns
    (submissions, assignment_name, error)."""
    subs, err = _canvas_get_all(
        f"/api/v1/courses/{course_id}/students/submissions",
        {"student_ids[]": ["all"], "assignment_ids[]": [assignment_id],
         "include[]": ["assignment", "user"], "per_page": 100},
    )
    if err:
        return None, "", err
    adata, _ = _canvas_get(f"/api/v1/courses/{course_id}/assignments/{assignment_id}")
    name = (adata or {}).get("name") or assignment_id
    return subs, name, None


@router.get("/run/prepare")
def feedback_run_prepare(
    course_id: str = Query(""),
    assignment_id: str = Query(""),
    rubric_name: str = Query(""),
):
    """Fetch + pseudonymize + HARD safety gate + write bundle. No paid call.
    Returns the token estimate so the client can confirm cost before /run/stream."""
    if not course_id or not assignment_id:
        return JSONResponse({"ok": False, "error": "course_id and assignment_id are required."})
    # No OpenRouter key gate here: generating the SAFE bundle is a local, free
    # operation (fetch → pseudonymize → scrub → write SAFE/PRIVATE). It is the
    # primary path for the own-LLM workflow. Only the paid /run/stream step needs
    # a key, and it checks for one itself.

    subs, assignment_name, err = _fetch_submissions(course_id, assignment_id)
    if err:
        return JSONResponse({"ok": False, "error": err})
    if not subs:
        return JSONResponse({"ok": False, "error": "No submissions returned for this assignment."})

    _enrich_with_code_files(subs)              # fold in .py/.html uploads as scored text
    vault = _vault()
    bundle = fp.pseudonymize_submissions(subs, vault, assignment_name)
    if not bundle["students"]:
        return JSONResponse({"ok": False, "error": "No written submissions to score for this assignment."})
    vault.save()

    verdict = safety.scan_payload(bundle, vault)
    if not verdict["green"]:
        _audit({"action": "blocked", "assignment": assignment_name,
                "course": course_id, "hard": len(verdict["hard"])})
        return JSONResponse({"ok": False, "green": False,
                             "error": "PII safety gate blocked this batch.",
                             "hard": verdict["hard"][:5]})

    # Write scrubbed SAFE bundle + PRIVATE copy + who-is-who. The rubric is inlined
    # into the SAFE HOW-TO-SCORE so the teacher's own LLM gets prompt + rubric + work
    # as one self-contained package (it is teacher-authored, not student PII).
    rubric_text = _load_rubric_text(rubric_name)
    protected = config.active_protected_names()
    result = fp.write_safe_and_private(
        bundle, vault,
        workspace.feedback_folder("SAFE"),
        workspace.feedback_folder("PRIVATE"),
        config.get_persona().get("name") or _ai_ta_name(),
        protected=protected,
        submissions=subs,
        rubric_text=rubric_text,
    )
    if not result["safe_bundle"]:
        return JSONResponse({"ok": False, "error": f"SAFE write failed: {result['log']}"})

    tokens = orc.estimate_tokens(bundle, rubric_text)
    response_data = {"ok": True, "green": True, "soft": verdict["soft"],
                     "tokens": tokens, "students": len(bundle["students"]),
                     "bundle_name": os.path.basename(result["safe_bundle"]),
                     "assignment_name": assignment_name,
                     "has_key": config.has_openrouter_key(),
                     "attachment_only": result.get("attachment_only", [])}
    return JSONResponse(response_data)


@router.get("/run/stream")
def feedback_run_stream(
    bundle_name: str = Query(""),
    persona_id: str = Query("sage"),
    rubric_name: str = Query(""),
    pattern_id: str = Query("basic"),
):
    """SSE — score a bundle already prepared + cost-confirmed via /run/prepare.
    Re-scans safety (defense in depth), scores via OpenRouter, re-identifies →
    ToEnter CSV. Yields progress lines; final lines: 'FOLDER: <path>', '[exit 0]'."""
    if not bundle_name:
        return StreamingResponse(
            _sse(["!! No prepared bundle — run prepare first.", "[exit 1]"]),
            media_type="text/event-stream")
    if not config.has_openrouter_key():
        return StreamingResponse(
            _sse(["!! No OpenRouter API key saved — configure in Settings.", "[exit 1]"]),
            media_type="text/event-stream")

    def stream():
        try:
            forllm = workspace.feedback_folder("SAFE")
            bpath = os.path.join(forllm, os.path.basename(bundle_name))
            if not os.path.isfile(bpath):
                yield "!! Prepared bundle not found — run prepare again."
                yield "[exit 1]"
                return
            with open(bpath, encoding="utf-8") as f:
                bundle = json.load(f)

            vault = _vault()
            persona = config.get_persona(persona_id)
            patterns = config.list_feedback_patterns()
            fb_pattern = next((p for p in patterns if p["id"] == pattern_id),
                              patterns[0] if patterns else None)
            rubric_text = _load_rubric_text(rubric_name)
            assignment_name = bundle.get("quiz_title", "assignment")

            # Defense in depth: re-scan the bundle right before it leaves.
            yield "Re-checking PII safety gate…"
            verdict = safety.scan_payload(bundle, vault)
            if not verdict["green"]:
                yield f"⛔ SAFETY BLOCK: {verdict['hard'][:2]}"
                _audit({"action": "blocked", "assignment": assignment_name,
                        "hard": len(verdict["hard"])})
                yield "[exit 1]"
                return

            yield f"Scoring {len(bundle['students'])} student(s) via OpenRouter…"
            results = orc.score(
                bundle, rubric_text, persona,
                api_key=config.get_openrouter_key(),
                model=config.get_openrouter_model(),
                feedback_pattern=fb_pattern,
            )

            yield f"Re-identifying {len(results)} result(s)…"
            rows = fp.reidentify(results, vault)
            toenter = workspace.feedback_folder("PRIVATE")
            os.makedirs(toenter, exist_ok=True)
            stem = fp._safe(assignment_name)
            dest = os.path.join(toenter, f"{stem}__to-enter.csv")
            with open(dest, "w", encoding="utf-8", newline="") as f:
                f.write(fp.reidentified_csv(rows))
            unresolved = sum(1 for r in rows if not r["resolved"])
            note = f" ({unresolved} unresolved)" if unresolved else ""
            yield f"✓ {assignment_name}: {len(rows)} scored{note} → ToEnter (review before posting)"
            _audit({"action": "guided_score", "assignment": assignment_name,
                    "persona": persona_id, "pattern": pattern_id,
                    "responses": len(rows)})
            yield f"FOLDER: {toenter}"
            yield "[exit 0]"

        except Exception as e:
            yield f"!! Fatal: {e}"
            yield "[exit 1]"

    return StreamingResponse(_sse(stream()), media_type="text/event-stream")


# ======================================================================
# Phase C — Push to Canvas (grade + comment). The teacher pastes the JSON
# their LLM produced (contract shape), we validate + re-identify locally,
# show a review preview with the CURRENT Canvas grade, and only on explicit
# confirm PUT posted_grade + text_comment per selected row. Assignments only.
# ======================================================================

def _current_scores(course_id: str, assignment_id: str) -> dict:
    """Map user_id(str) -> current Canvas score for this assignment (idempotency:
    we show the teacher what's already there before overwriting)."""
    subs, _ = _canvas_get_all(
        f"/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions",
        {"per_page": 100})
    return {str(s.get("user_id")): s.get("score") for s in (subs or [])}


def _load_safe_bundle(course_id: str, assignment_id: str):
    """Best-effort load of the SAFE bundle for this assignment so the validator can
    cross-check coverage + score ranges. Returns the bundle dict or None."""
    adata, _ = _canvas_get(f"/api/v1/courses/{course_id}/assignments/{assignment_id}")
    name = (adata or {}).get("name") or assignment_id
    safe_dir = workspace.feedback_folder("SAFE")
    if not safe_dir:
        return None
    path = os.path.join(safe_dir, f"{fp._safe(name)}__bundle.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


@router.post("/push/preview")
def feedback_push_preview(course_id: str = Form(""), assignment_id: str = Form(""),
                          results: str = Form("")):
    """Validate pasted LLM results + re-identify + join the current Canvas grade.
    No writes. Hard validation errors block; warnings are returned for display."""
    if not course_id or not assignment_id:
        return JSONResponse({"ok": False, "error": "course_id and assignment_id are required."})
    if not results.strip():
        return JSONResponse({"ok": False, "error": "Paste the scored JSON from your LLM first."})
    try:
        parsed = fp.parse_results(results)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"Could not parse JSON: {e}"})

    vault = _vault()
    bundle = _load_safe_bundle(course_id, assignment_id)
    verdict = fp.validate_results(parsed, bundle, vault)
    if not verdict["ok"]:
        return JSONResponse({"ok": False, "error": "Validation failed — fix and re-paste.",
                             "validation": verdict})

    rows = fp.reidentify(parsed, vault)
    current = _current_scores(course_id, assignment_id)
    preview = []
    for r in rows:
        uid = str(r["canvas_id"])
        cur = current.get(uid)
        preview.append({
            "canvas_id": uid,
            "real_name": r["real_name"],
            "resolved": r["resolved"],
            "score": r["score"],
            "feedback": r["feedback"],
            "current_grade": cur,
            "already_graded": cur is not None,
        })
    return JSONResponse({"ok": True, "validation": verdict, "rows": preview})


def _push_payload(row: dict) -> dict:
    """Canvas submission PUT body for one re-identified row. score=null -> comment
    only (posted_grade omitted); empty feedback -> grade only; empty both -> {}."""
    payload = {}
    score = row.get("score", None)
    if score is not None:
        payload["submission"] = {"posted_grade": str(score)}
    fb = (row.get("feedback") or "").strip()
    if fb:
        payload["comment"] = {"text_comment": fb}
    return payload


@router.post("/push/apply")
def feedback_push_apply(course_id: str = Form(""), assignment_id: str = Form(""),
                        rows: str = Form("")):
    """Push the teacher-selected rows to Canvas: PUT posted_grade + text_comment per
    submission. score=null -> comment-only (posted_grade omitted). Explicit, post-
    confirmation. Audit stays content-free (counts only — never names/scores/feedback)."""
    if not course_id or not assignment_id:
        return JSONResponse({"ok": False, "error": "course_id and assignment_id are required."})
    try:
        selected = json.loads(rows) if rows.strip() else []
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": f"bad rows: {e}"})
    if not selected:
        return JSONResponse({"ok": False, "error": "No rows selected to push."})

    base_path = f"/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions"
    posted, errors = 0, []
    for r in selected:
        uid = str(r.get("canvas_id", ""))
        if not uid:
            continue
        payload = _push_payload(r)
        if not payload:
            continue                       # nothing to post for this row
        _, err = _canvas_send("PUT", f"{base_path}/{uid}", payload)
        if err:
            errors.append({"canvas_id": uid, "error": err})
        else:
            posted += 1
    _audit({"action": "push", "course": course_id, "assignment": assignment_id,
            "posted": posted, "errors": len(errors)})
    return JSONResponse({"ok": True, "posted": posted, "errors": errors,
                         "total": len(selected)})
