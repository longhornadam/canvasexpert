"""Gradebook due-date extension routes."""
import json

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from .. import deps, school_calendar
from api.platform_services.canvas_client import canvas_get, _canvas_send
from ..schooldays import parse_iso_local

router = APIRouter(tags=["gradebook"])


@router.post("/api/extend-due")
def extend_due(course_id: str = Form(...), assignment_id: str = Form(...),
               student_ids: str = Form(...), days: int = Form(...)):
    """Give specific students +N school days on one assignment."""
    try:
        sids = json.loads(student_ids)
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": f"bad request: {e}"})
    if not sids:
        return JSONResponse({"ok": False, "error": "no students selected"})

    a, err = canvas_get(f"/api/v1/courses/{course_id}/assignments/{assignment_id}")
    if err:
        return JSONResponse({"ok": False, "error": err})
    due = parse_iso_local(a.get("due_at"))
    if not due:
        return JSONResponse({"ok": False,
                             "error": "assignment has no due date — set one in Canvas first"})

    # Resolve the requested addition before any Canvas send: a broken or
    # out-of-range calendar refuses here rather than silently writing an
    # override computed with weekends counted as school days.
    bell_schedules, _problems = deps.load_bell_schedules()
    new_due, failure = school_calendar.add_school_days_checked(due, days, set(bell_schedules))
    if failure is not None:
        return JSONResponse({"ok": False, "error": school_calendar.CALENDAR_REPAIR_MESSAGE,
                             "problems": failure["problems"]})
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
