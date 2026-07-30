"""Shared current-course authorization helpers for read adapters."""
from __future__ import annotations


def current_course_ids(courses: list[dict]) -> set[str]:
    return {
        str(course.get("id") or "").strip()
        for course in courses or []
        if str(course.get("id") or "").strip()
        and course.get("active", True)
    }


def current_course_error(course_id: str, courses: list[dict]) -> str | None:
    if str(course_id) not in current_course_ids(courses):
        return f"course_id '{course_id}' is not a Current course in CanvasExpert."
    return None
