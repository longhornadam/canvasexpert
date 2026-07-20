"""Student-free Canvas course lifecycle context for mirror scheduling.

The module has no Canvas client dependency: callers inject the one-object and
paginated GET seams.  It normalizes a deliberately tiny allowlist, commits only
that record through ``store``, and never raises a transport or validation error
into the heartbeat scheduler.
"""
from __future__ import annotations

from api.mirror import store


ENROLLMENT_STATES = ("active", "invited", "completed", "inactive")


def _iso_z(value) -> str:
    """Return an ISO-Z timestamp or the allowed empty value."""
    return value if isinstance(value, str) and store._valid_iso_z(value) else ""


def normalize_course(row) -> dict:
    """Keep exactly the course/term fields permitted in course_context.v1."""
    if not isinstance(row, dict):
        raise ValueError("invalid_response")
    term = row.get("term") if isinstance(row.get("term"), dict) else {}
    return {
        "course_workflow_state": (row.get("workflow_state")
                                  if isinstance(row.get("workflow_state"), str) else ""),
        "course_concluded": row.get("concluded") is True,
        "course_end_at": _iso_z(row.get("end_at")),
        "term_end_at": _iso_z(term.get("end_at")),
    }


def normalize_enrollment_states(rows) -> list[str]:
    """Return distinct caller enrollment states in a deterministic allowlist order."""
    if not isinstance(rows, list):
        raise ValueError("invalid_response")
    seen = {
        str(row.get("enrollment_state") or "")
        for row in rows
        if isinstance(row, dict)
    }
    return [state for state in ENROLLMENT_STATES if state in seen]


def classify_lifecycle(enrollment_states: list[str]) -> str:
    """Active wins; a completed/inactive-only result is concluded; otherwise unknown."""
    states = set(enrollment_states)
    if "active" in states:
        return "current"
    if states & {"completed", "inactive"}:
        return "concluded"
    return "unknown"


def sanitized_error_code(error) -> str:
    """Map transport/validation errors to the stable, non-sensitive context codes."""
    text = str(error or "").lower()
    if "invalid_response" in text or "malformed" in text or "json" in text:
        return "invalid_response"
    if "http 401" in text or "unauthorized" in text:
        return "unauthorized"
    if "http 403" in text or "forbidden" in text:
        return "forbidden"
    if "http 404" in text or "not found" in text:
        return "not_found"
    if "http 429" in text or "rate" in text:
        return "rate_limited"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    return "connection"


def refresh_course_context(course_id, *, canvas_get, canvas_get_all, root=None,
                           now=None) -> dict:
    """Fetch and persist one course's caller-only lifecycle proof.

    Failures retain the last-good lifecycle fields by delegating envelope
    degradation to ``store.record_course_context``.  Raw Canvas rows are kept
    only in local variables and discarded before the write.
    """
    attempted_at = now or store.now_iso()
    try:
        course, error = canvas_get(
            f"/api/v1/courses/{course_id}", {"include[]": "concluded"})
        if error:
            return store.record_course_context(
                course_id, ok=False, attempted_at=attempted_at,
                error_code=sanitized_error_code(error), root=root)
        course_fields = normalize_course(course)

        enrollments, error = canvas_get_all(
            f"/api/v1/courses/{course_id}/enrollments",
            {"user_id": "self", "per_page": 100, "state[]": list(ENROLLMENT_STATES)})
        if error:
            return store.record_course_context(
                course_id, ok=False, attempted_at=attempted_at,
                error_code=sanitized_error_code(error), root=root)
        enrollment_states = normalize_enrollment_states(enrollments)
        return store.record_course_context(
            course_id, ok=True, attempted_at=attempted_at,
            lifecycle=classify_lifecycle(enrollment_states),
            enrollment_states=enrollment_states, root=root, **course_fields)
    except Exception as error:
        # The lifecycle scope is advisory scheduling context.  A malformed or
        # unavailable read must not escape into or interrupt core mirror work.
        return store.record_course_context(
            course_id, ok=False, attempted_at=attempted_at,
            error_code=sanitized_error_code(error), root=root)


def ensure_course_context(course_id, *, canvas_get, canvas_get_all, root=None,
                          now=None, max_age_hours: float = 24.0) -> dict:
    """Refresh on first use and no more often than the lifecycle daily cadence."""
    now_iso = now or store.now_iso()
    existing = store.read_course_context(course_id, root=root)
    age = store.age_hours(existing["last_attempt_at"], now_iso)
    if age is not None and age < max_age_hours:
        return existing
    return refresh_course_context(course_id, canvas_get=canvas_get,
                                  canvas_get_all=canvas_get_all, root=root,
                                  now=now_iso)
