"""Gradebook due-date extension routes."""
import json

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from .. import config
from ..canvas_client import _canvas_get, _canvas_send
from ..schooldays import _add_school_days, _parse_iso_local

router = APIRouter(tags=["gradebook"])


@router.post("/api/extend-due")
def extend_due(course_id: str = Form(...), assignment_id: str = Form(...),
               student_ids: str = Form(...), days: int = Form(...),
               skip_weekends: str = Form("true"), holidays: str = Form("[]")):
    """Give specific students +N school days on one assignment."""
    try:
        sids = json.loads(student_ids)
        hols = set(json.loads(holidays))
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": f"bad request: {e}"})
    if not sids:
        return JSONResponse({"ok": False, "error": "no students selected"})
    skip_we = skip_weekends.lower() in ("true", "1", "yes")
    hols.update(config.get_combined_calendar_for_range().get("no_count_dates") or [])

    a, err = _canvas_get(f"/api/v1/courses/{course_id}/assignments/{assignment_id}")
    if err:
        return JSONResponse({"ok": False, "error": err})
    due = _parse_iso_local(a.get("due_at"))
    if not due:
        return JSONResponse({"ok": False,
                             "error": "assignment has no due date — set one in Canvas first"})

    new_due = _add_school_days(due, days, skip_we, hols)
    resp, err = _canvas_send(
        "POST", f"/api/v1/courses/{course_id}/assignments/{assignment_id}/overrides",
        {"assignment_override": {
            "student_ids": sids,
            "title": f"Extra time (+{days} school day{'s' if days != 1 else ''})",
            "due_at": new_due.isoformat(),
        }})
    if err:
        hint = (" (a student can only be in one override per assignment — "
                "check existing overrides in Canvas)" if "400" in err else "")
        return JSONResponse({"ok": False, "error": err + hint})
    return JSONResponse({"ok": True,
                         "assignment": a.get("name", ""),
                         "new_due": new_due.isoformat(),
                         "count": len(sids)})
