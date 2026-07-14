"""Feedback tools assignment-driven prepare and OpenRouter scoring stream."""
import json
import os
import glob

import requests
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, StreamingResponse

import feedback_pipeline as fp
import feedback_safety as safety
import openrouter_client as orc
from .. import config, workspace
from ..canvas_client import _canvas_get, _canvas_get_all, _canvas_headers
from ..deps import _sse
from .feedback_common import (
    ai_ta_name,
    audit,
    budget_error_message,
    load_rubric_text,
    vault,
)

router = APIRouter()

_CODE_EXTS = {".py", ".html", ".htm", ".css", ".js", ".txt", ".md", ".json", ".csv"}
_MAX_CODE_BYTES = 256 * 1024


def _enrich_with_code_files(subs):
    """Attach text/code upload contents to submissions before pseudonymization."""
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
    """Fetch one assignment's submissions. Returns (submissions, assignment_name, error)."""
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
    """Fetch, pseudonymize, safety-check, and write SAFE/PRIVATE artifacts."""
    if not course_id or not assignment_id:
        return JSONResponse({"ok": False, "error": "course_id and assignment_id are required."})

    subs, assignment_name, err = _fetch_submissions(course_id, assignment_id)
    if err:
        return JSONResponse({"ok": False, "error": err})
    if not subs:
        return JSONResponse({"ok": False, "error": "No submissions returned for this assignment."})

    _enrich_with_code_files(subs)
    v = vault()
    bundle = fp.pseudonymize_submissions(subs, v, assignment_name)
    if not bundle["students"]:
        return JSONResponse({"ok": False, "error": "No written submissions to score for this assignment."})
    v.save()

    verdict = safety.scan_payload(bundle, v)
    if not verdict["green"]:
        audit({"action": "blocked", "assignment": assignment_name,
               "course": course_id, "hard": len(verdict["hard"])})
        return JSONResponse({"ok": False, "green": False,
                             "error": "PII safety gate blocked this batch.",
                             "hard": verdict["hard"][:5]})

    rubric_text = load_rubric_text(rubric_name)
    protected = config.active_protected_names()
    persona = config.get_persona()
    result = fp.write_safe_and_private(
        bundle, v,
        workspace.ai_packets_root(),
        workspace.courses_root(),
        persona.get("name") or ai_ta_name(),
        persona=persona,
        protected=protected,
        submissions=subs,
        rubric_text=rubric_text,
    )
    if not result["safe_bundle"]:
        return JSONResponse({"ok": False, "error": f"SAFE write failed: {result['log']}"})

    tokens = orc.estimate_tokens(bundle, rubric_text)
    model = config.get_openrouter_model()
    budget = orc.teacher_workflow_budget(
        bundle,
        rubric_text,
        model,
        student_count=len(bundle["students"]),
    ) if config.has_openrouter_key() else None
    return JSONResponse({"ok": True, "green": True, "soft": verdict["soft"],
                         "tokens": tokens, "students": len(bundle["students"]),
                         "bundle_name": os.path.basename(result["safe_bundle"]),
                         "assignment_name": assignment_name,
                         "model": model,
                         "budget": budget,
                         "has_key": config.has_openrouter_key(),
                         "attachment_only": result.get("attachment_only", [])})


@router.get("/run/stream")
def feedback_run_stream(
    bundle_name: str = Query(""),
    persona_id: str = Query("sage"),
    rubric_name: str = Query(""),
    pattern_id: str = Query("basic"),
):
    """Score a prepared bundle over SSE after explicit cost confirmation."""
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
            forllm = workspace.ai_packets_root()
            candidates = glob.glob(os.path.join(forllm, "**", os.path.basename(bundle_name)), recursive=True)
            bpath = sorted(candidates, key=lambda p: os.path.getmtime(p), reverse=True)[0] if candidates else ""
            if not bpath or not os.path.isfile(bpath):
                yield "!! Prepared bundle not found — run prepare again."
                yield "[exit 1]"
                return
            with open(bpath, encoding="utf-8") as f:
                bundle = json.load(f)

            v = vault()
            persona = config.get_persona(persona_id)
            patterns = config.list_feedback_patterns()
            fb_pattern = next((p for p in patterns if p["id"] == pattern_id),
                              patterns[0] if patterns else None)
            rubric_text = load_rubric_text(rubric_name)
            assignment_name = bundle.get("quiz_title", "assignment")

            yield "Re-checking PII safety gate…"
            verdict = safety.scan_payload(bundle, v)
            if not verdict["green"]:
                yield f"⛔ SAFETY BLOCK: {verdict['hard'][:2]}"
                audit({"action": "blocked", "assignment": assignment_name,
                       "hard": len(verdict["hard"])})
                yield "[exit 1]"
                return

            model = config.get_openrouter_model()
            budget = orc.teacher_workflow_budget(
                bundle,
                rubric_text,
                model,
                student_count=len(bundle.get("students") or []),
            )
            if not budget["ok"]:
                yield f"⛔ COST BLOCK: {budget_error_message(budget)}"
                audit({"action": "blocked_cost", "assignment": assignment_name,
                       "model": model, "tokens_est": budget.get("input_tokens")})
                yield "[exit 1]"
                return

            yield f"Scoring {len(bundle['students'])} student(s) via OpenRouter ({model})…"
            results = orc.score(
                bundle, rubric_text, persona,
                api_key=config.get_openrouter_key(),
                model=model,
                feedback_pattern=fb_pattern,
            )

            yield f"Re-identifying {len(results)} result(s)…"
            rows = fp.reidentify(results, v)
            toenter = workspace.courses_root()
            os.makedirs(toenter, exist_ok=True)
            stem = fp._safe(assignment_name)
            dest = os.path.join(toenter, f"{stem}__to-enter.csv")
            with open(dest, "w", encoding="utf-8", newline="") as f:
                f.write(fp.reidentified_csv(rows))
            unresolved = sum(1 for r in rows if not r["resolved"])
            note = f" ({unresolved} unresolved)" if unresolved else ""
            yield f"✓ {assignment_name}: {len(rows)} scored{note} → ToEnter (review before posting)"
            audit({"action": "guided_score", "assignment": assignment_name,
                   "persona": persona_id, "pattern": pattern_id,
                   "responses": len(rows)})
            yield f"FOLDER: {toenter}"
            yield "[exit 0]"
        except Exception as e:
            yield f"!! Fatal: {e}"
            yield "[exit 1]"

    return StreamingResponse(_sse(stream()), media_type="text/event-stream")
