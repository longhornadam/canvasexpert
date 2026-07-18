"""Compatibility aliases for the shared Gradebook read use cases."""
from api.gradebook_queries import (
    assignment as _assignment,
    assignment_submissions as _assignment_submissions,
    course_assignments as _course_assignments,
    course_students as _course_students,
    course_submissions as _course_submissions,
)
from api.mirror import store as mirror_store


def _roster_students_or_none(course_id):
    """Student-list rows from a current roster mirror, or ``None`` to signal
    the existing live ``_course_students`` fallback (1.0beta-04a; extra-time
    list only — curve/snapshot/mcp/operation-ledger consumers keep importing
    the live-only ``_course_students`` above unchanged).

    Reuses the same roster mirror read as ``courses.py``'s ``_local_students``
    (state == "current"; the roster mirror carries no age/TTL policy). Rows
    come from ``normalize_student``, which never stores email — private-lean
    at rest, so this never needs to filter a field out.
    """
    document = mirror_store.read_roster(course_id)
    if not isinstance(document, dict) or document.get("state") != "current":
        return None
    students = document.get("students")
    if not isinstance(students, dict):
        return None
    try:
        return [
            {"id": student["id"],
             "name": student.get("name", ""),
             "sortable_name": student.get("sortable_name") or student.get("name", "")}
            for student in students.values()
        ]
    except (AttributeError, KeyError):
        return None
