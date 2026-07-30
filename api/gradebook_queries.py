"""Canvas read use cases shared by HTTP and MCP adapters."""
from __future__ import annotations

from api.webui.canvas_client import _canvas_get, _canvas_get_all


def course_students(course_id: str):
    return _canvas_get_all(
        f"/api/v1/courses/{course_id}/users",
        {"enrollment_type[]": "student", "per_page": 100},
    )


def course_assignments(course_id: str):
    return _canvas_get_all(
        f"/api/v1/courses/{course_id}/assignments",
        {"per_page": 100},
    )


def course_submissions(course_id: str):
    return _canvas_get_all(
        f"/api/v1/courses/{course_id}/students/submissions",
        {"student_ids[]": "all", "per_page": 100},
        timeout=60,
    )


def assignment(course_id: str, assignment_id: str):
    return _canvas_get(f"/api/v1/courses/{course_id}/assignments/{assignment_id}")


def assignment_submissions(course_id: str, assignment_id: str):
    return _canvas_get_all(
        f"/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions",
        {"per_page": 100},
    )
