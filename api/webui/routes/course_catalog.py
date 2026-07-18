"""Current-course-gated local read and read-only refresh routes."""

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from api import assignment_collection, course_catalog
from api.mirror import sync as mirror_sync

from .. import config
from ..canvas_client import _canvas_get_all, _canvas_get_all_complete


router = APIRouter(tags=["course-catalog"])


def _current_course(course_id: str) -> dict | None:
    wanted = str(course_id or "").strip()
    if not wanted:
        return None
    return next(
        (course for course in config.active_courses() if str(course.get("id") or "").strip() == wanted),
        None,
    )


def _gate_error():
    return JSONResponse({"ok": False, "error": "Select a saved current course first."})


@router.get("/api/course-catalog")
def get_course_catalog(course_id: str = ""):
    """Read the local snapshot only; this route never contacts Canvas."""
    course = _current_course(course_id)
    if course is None:
        return _gate_error()
    result = course_catalog.read_catalog(str(course["id"]))
    return JSONResponse(course_catalog.public_projection(result, course_id=str(course["id"])))


@router.post("/api/course-catalog/refresh")
def refresh_course_catalog(course_id: str = Form("")):
    course = _current_course(course_id)
    if course is None:
        return _gate_error()
    course_id = str(course["id"])
    course_name = str(course.get("nickname") or course.get("name") or course_id)
    try:
        receipt = assignment_collection.acquire_assignment_collection(
            course_id, _canvas_get_all_complete)
    except (OSError, ValueError):
        return JSONResponse({"ok": False, "error": "The course list could not be synchronized."})

    catalog_failure = False
    try:
        result = course_catalog.refresh_catalog(
            course_id,
            course_name,
            canvas_get_all=_canvas_get_all,
            canvas_get_all_complete=_canvas_get_all_complete,
            assignment_receipt=receipt,
        )
    except (OSError, ValueError):
        catalog_failure = True

    try:
        mirror_sync.apply_assignment_collection_receipt(course_id, receipt)
    except (OSError, ValueError):
        pass

    if catalog_failure:
        return JSONResponse({"ok": False, "error": "The course list could not be synchronized."})
    return JSONResponse(course_catalog.public_projection(result, course_id=course_id))
