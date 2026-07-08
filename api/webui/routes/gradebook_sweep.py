"""Gradebook school-day sweep routes."""
import json

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from .. import config
from ..canvas_client import _canvas_send
from ..gradebook_service import _sweep_compute

router = APIRouter(tags=["gradebook"])


@router.post("/api/sweep/preview")
def sweep_preview(course_id: str = Form(...), settings: str = Form(...)):
    """Dry run - compute every late deduction + the comment text, change nothing."""
    try:
        s = json.loads(settings)
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": f"bad request: {e}"})
    config.set_sweep_settings(s)
    entries, skipped, err = _sweep_compute(course_id, s)
    if err:
        return JSONResponse({"ok": False, "error": err})
    return JSONResponse({"ok": True, "entries": entries, "skipped": skipped})


@router.post("/api/sweep/apply")
def sweep_apply(course_id: str = Form(...), entries: str = Form(...)):
    """Push seconds_late_override to Canvas for selected late submissions."""
    try:
        rows = json.loads(entries)
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": f"bad request: {e}"})
    if not rows:
        return JSONResponse({"ok": False, "error": "no rows selected"})

    results = []
    for r in rows:
        _, err = _canvas_send(
            "PUT",
            f"/api/v1/courses/{course_id}/assignments/{r['assignment_id']}/submissions/{r['user_id']}",
            {"submission": {
                "late_policy_status": "late",
                "seconds_late_override": r["seconds_override"],
            }})
        results.append({
            "student": r.get("student_name", r["user_id"]),
            "assignment": r.get("assignment_name", r["assignment_id"]),
            "school_days": r["school_days"],
            "ok": not err, "error": err,
        })
    return JSONResponse({"ok": all(x["ok"] for x in results), "results": results})
