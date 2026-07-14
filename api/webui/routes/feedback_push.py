"""Feedback tools push-preview and Canvas write routes."""
import json
import os
import glob

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

import feedback_pipeline as fp
from .. import workspace
from ..canvas_client import _canvas_get, _canvas_get_all, _canvas_send
from .feedback_common import audit, vault

router = APIRouter()


def _current_scores(course_id: str, assignment_id: str) -> dict:
    """Map user_id(str) -> current Canvas score for this assignment."""
    subs, _ = _canvas_get_all(
        f"/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions",
        {"per_page": 100})
    return {str(s.get("user_id")): s.get("score") for s in (subs or [])}


def _load_safe_bundle(course_id: str, assignment_id: str):
    """Best-effort load of the SAFE bundle for this assignment."""
    adata, _ = _canvas_get(f"/api/v1/courses/{course_id}/assignments/{assignment_id}")
    name = (adata or {}).get("name") or assignment_id
    safe_dir = workspace.ai_packets_root()
    if not safe_dir:
        return None
    candidates = glob.glob(os.path.join(safe_dir, "**", f"{fp._safe(name)}__bundle.json"), recursive=True)
    if not candidates:
        return None
    path = sorted(candidates, key=lambda p: os.path.getmtime(p), reverse=True)[0]
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


@router.post("/push/preview")
def feedback_push_preview(course_id: str = Form(""), assignment_id: str = Form(""),
                          results: str = Form("")):
    """Validate pasted LLM results, re-identify, and show current Canvas grade."""
    if not course_id or not assignment_id:
        return JSONResponse({"ok": False, "error": "course_id and assignment_id are required."})
    if not results.strip():
        return JSONResponse({"ok": False, "error": "Paste the scored JSON from your LLM first."})
    try:
        parsed = fp.parse_results(results)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"Could not parse JSON: {e}"})

    v = vault()
    bundle = _load_safe_bundle(course_id, assignment_id)
    verdict = fp.validate_results(parsed, bundle, v)
    if not verdict["ok"]:
        return JSONResponse({"ok": False, "error": "Validation failed — fix and re-paste.",
                             "validation": verdict})

    rows = fp.reidentify(parsed, v)
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
    """Canvas submission PUT body for one re-identified row."""
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
    """Push teacher-selected grades/comments to Canvas after explicit confirmation."""
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
            continue
        _, err = _canvas_send("PUT", f"{base_path}/{uid}", payload)
        if err:
            errors.append({"canvas_id": uid, "error": err})
        else:
            posted += 1
    audit({"action": "push", "course": course_id, "assignment": assignment_id,
           "posted": posted, "errors": len(errors)})
    return JSONResponse({"ok": True, "posted": posted, "errors": errors,
                         "total": len(selected)})
