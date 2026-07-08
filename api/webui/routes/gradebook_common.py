"""Shared helpers for Gradebook route modules."""
from ..canvas_client import _canvas_get, _canvas_get_all


def _course_students(course_id: str):
    return _canvas_get_all(
        f"/api/v1/courses/{course_id}/users",
        {"enrollment_type[]": "student", "per_page": 100},
    )


def _course_assignments(course_id: str):
    return _canvas_get_all(
        f"/api/v1/courses/{course_id}/assignments",
        {"per_page": 100},
    )


def _course_submissions(course_id: str):
    return _canvas_get_all(
        f"/api/v1/courses/{course_id}/students/submissions",
        {"student_ids[]": "all", "per_page": 100},
        timeout=60,
    )


def _assignment(course_id: str, assignment_id: str):
    return _canvas_get(f"/api/v1/courses/{course_id}/assignments/{assignment_id}")


def _assignment_submissions(course_id: str, assignment_id: str):
    return _canvas_get_all(
        f"/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions",
        {"per_page": 100},
    )
