"""Gradebook whole-course snapshot route and compatibility seam."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .gradebook_common import _course_assignments, _course_students, _course_submissions
from api import gradebook_snapshot as _shared_snapshot

router = APIRouter(tags=["gradebook"])


build_snapshot = _shared_snapshot.build_snapshot
_ORIGINAL_COURSE_STUDENTS = _course_students
_ORIGINAL_COURSE_ASSIGNMENTS = _course_assignments
_ORIGINAL_COURSE_SUBMISSIONS = _course_submissions


def load_snapshot(course_id: str):
    """Route test seam delegating to the shared loader."""
    if (
        _course_students is _ORIGINAL_COURSE_STUDENTS
        and _course_assignments is _ORIGINAL_COURSE_ASSIGNMENTS
        and _course_submissions is _ORIGINAL_COURSE_SUBMISSIONS
    ):
        return _shared_snapshot.load_snapshot(course_id)
    queries = type("RouteQueries", (), {
        "course_students": staticmethod(_course_students),
        "course_assignments": staticmethod(_course_assignments),
        "course_submissions": staticmethod(_course_submissions),
    })
    return _shared_snapshot.load_snapshot(course_id, queries=queries)


@router.get("/api/gradebook")
def api_gradebook(course_id: str):
    """Whole-course grading snapshot: per-assignment and per-student stats."""
    snapshot, err = load_snapshot(course_id)
    if err:
        return JSONResponse({"ok": False, "error": err})
    snapshot["students"] = [
        {k: v for k, v in s.items() if k != "user_id"}
        for s in snapshot["students"]
    ]
    return JSONResponse(snapshot)
