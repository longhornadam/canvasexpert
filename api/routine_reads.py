"""Typed, mirror-first read interface for built-in and custom Routines.

One explicit mapping from a named scope to (a) the ``read_service`` freshness
check, (b) the matching ``mirror_queries`` accessor, and (c) the exact live
Canvas endpoint/params ``api/webui/mirror_reads.py`` already uses for that
same collection. This module owns no Canvas import and no persistence: a
live fallback is only ever made through the caller-injected ``live_reader``
(callers pass ``_canvas_get_all``; tests inject fakes), and only for the
three named scopes below. Unknown scopes are rejected with a structured
result — never resolved to an arbitrary URL.

``read_scope`` always returns the same shape: ``ok, records, error, source,
synced_at, generation``. A mirror-served result never leaves ``synced_at``/
``generation`` empty; a live-served result never claims either (source
labeling only, per design law #4) — callers that ignore source metadata
(built-ins) must not serialize it back out; custom-routine authors receive
the full dict.
"""
from __future__ import annotations

from api.mirror import queries as mirror_queries
from api.mirror import read_service

# scope -> (read_service freshness check, mirror_queries accessor,
#           live endpoint path template, live params, live extra kwargs)
_SCOPES = {
    "assignments": (
        read_service.private_assignments,
        mirror_queries.course_assignments,
        lambda course_id: f"/api/v1/courses/{course_id}/assignments",
        {"per_page": 100},
        {},
    ),
    "roster": (
        read_service.private_roster,
        mirror_queries.course_students,
        lambda course_id: f"/api/v1/courses/{course_id}/users",
        {"enrollment_type[]": "student", "per_page": 100},
        {},
    ),
    "submissions": (
        read_service.private_submissions,
        mirror_queries.course_submissions,
        lambda course_id: f"/api/v1/courses/{course_id}/students/submissions",
        {"student_ids[]": "all", "per_page": 100},
        {"timeout": 60},
    ),
}


def _rejected(scope) -> dict:
    return {
        "ok": False,
        "records": [],
        "error": f"unsupported scope: {scope!r}",
        "source": "",
        "synced_at": "",
        "generation": "",
    }


def read_scope(scope, course_id, *, live_reader, max_age_hours=None):
    """``{ok, records, error, source, synced_at, generation}`` for one of the
    three supported course-scoped collections, mirror-first.

    A current typed scope makes zero live calls. Missing/stale/corrupt state
    calls ``live_reader(path, params, **extra)`` with the exact endpoint and
    params ``mirror_reads.py`` uses for that scope, and labels the result
    ``source="canvas"`` with no freshness/generation claim.
    """
    entry = _SCOPES.get(scope)
    if entry is None:
        return _rejected(scope)
    private_reader, mirror_read, path_for, params, extra = entry

    age = mirror_queries._serve_max_age_hours() if max_age_hours is None else max_age_hours
    state = private_reader(course_id, max_age_hours=age)
    if state["state"] == "current":
        rows, error = mirror_read(course_id)
        if not error and isinstance(rows, list):
            return {
                "ok": True,
                "records": rows,
                "error": None,
                "source": "mirror",
                "synced_at": state["last_success_at"],
                "generation": state["generation"],
            }

    rows, error = live_reader(path_for(course_id), dict(params), **extra)
    return {
        "ok": not error,
        "records": rows if isinstance(rows, list) else [],
        "error": error,
        "source": "canvas",
        "synced_at": "",
        "generation": "",
    }
