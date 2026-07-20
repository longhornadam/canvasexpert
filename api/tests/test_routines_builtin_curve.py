"""Batch 7 unit 02 — scheduled-routine curve write-through reconciliation.

`_run_routine_curve` writes curved grades to Canvas via `_curve_apply_core`.
After each course's whole curve batch it must fire exactly one coalesced
`mirror_service.notify_course_changed(course_id)` so mirror-backed grade reads
pick up the curved scores — once per course that curved at least one
assignment, never per assignment, never for a course that curved nothing, and
never in flag (non-apply) mode. This mirrors the direct curve routes and the
PowerGrader grade-push path; failure semantics are fire-and-forget with the
heartbeat as the backstop (no new stale-mark).

These tests isolate the coalescing behavior by stubbing the curve internals
(`_curve_apply_core`, `_apply_curve_model`) and recording the notify calls.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from api.webui.routes import routines_builtin

COURSE_A = "5001"  # will curve one assignment
COURSE_B = "5002"  # nothing to curve (average above floor)


def _recent_due() -> str:
    return (datetime.now().date() - timedelta(days=5)).isoformat() + "T09:00:00Z"


def _wire(monkeypatch):
    """Two active courses; A has a below-floor assignment, B is above floor.
    Returns the list that records notify_course_changed(course_id) calls."""
    monkeypatch.setattr(routines_builtin.config, "active_courses",
                        lambda: [{"id": COURSE_A, "nickname": "Course A"},
                                 {"id": COURSE_B, "nickname": "Course B"}])
    monkeypatch.setattr(routines_builtin, "students_or_live",
                        lambda cid: ([], None, "mirror"))
    monkeypatch.setattr(routines_builtin, "_load_curve_events", lambda: [])

    due = _recent_due()

    def fake_get_all(path, params=None, timeout=None):
        if path.endswith("/assignments"):
            aid = 111 if f"/courses/{COURSE_A}/" in path else 222
            return [{"id": aid, "name": "Quiz", "due_at": due,
                     "points_possible": 10, "published": True}], None
        if path.endswith("/submissions"):
            score = 5 if f"/courses/{COURSE_A}/" in path else 9  # A: 50% < 80; B: 90% >= 80
            return [{"user_id": str(i), "workflow_state": "graded", "score": score}
                    for i in range(3)], None
        return [], None

    monkeypatch.setattr(routines_builtin, "_canvas_get_all", fake_get_all)
    # Only reached for course A (B is skipped before the curve model); return a
    # single changed row so the curve is attempted.
    monkeypatch.setattr(routines_builtin, "_apply_curve_model",
                        lambda scored, model, settings, pts: [
                            {"user_id": "0", "original_score": 5, "curved_score": 8,
                             "changed": True}])

    applied_calls = []
    monkeypatch.setattr(routines_builtin, "_curve_apply_core",
                        lambda cid, aid, ctype, settings, rows:
                        (applied_calls.append((cid, aid)) or (True, "evt", [])))

    notified = []
    monkeypatch.setattr(routines_builtin.mirror_service, "notify_course_changed",
                        lambda course_id, **kw: notified.append(str(course_id)))
    return notified, applied_calls


def test_apply_mode_reconciles_once_for_the_curved_course_only(monkeypatch):
    notified, applied_calls = _wire(monkeypatch)

    result = routines_builtin._run_routine_curve({"mode": "apply", "floor": 80})

    assert result["ok"] is True
    # Course A curved one assignment; Course B curved nothing.
    assert applied_calls == [(COURSE_A, "111")]
    # Exactly one coalesced refresh, for the curved course, and not for course B.
    assert notified == [COURSE_A]


def test_flag_mode_never_reconciles(monkeypatch):
    notified, applied_calls = _wire(monkeypatch)

    result = routines_builtin._run_routine_curve({"mode": "flag", "floor": 80})

    # Flag mode identifies below-floor assignments but writes nothing.
    assert applied_calls == []
    assert notified == []
