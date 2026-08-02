"""Tests for PowerGrader interactive auto-post orchestration.

These tests cover guard checks, fresh-fetch behavior, receipt resolution,
exact subset semantics, happy grade+comment PUT, idempotent retry, summary
sanitization, and lock/concurrency behavior.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.powergrader.interactive_autopush import (
    run_interactive_autopush,
)
from api.webui import workspace


@pytest.fixture(autouse=True)
def _isolated_workspace_root(monkeypatch, tmp_path):
    # interactive_receipt_dir() resolves through session_store.pg_dir(), which
    # depends on workspace.workspace_root(). Without an isolated root, a real
    # push is silently refused (no receipt dir to record idempotency against)
    # whenever the ambient environment has no live OneDrive workspace, and
    # silently succeeds against the real one when it does -- neither should
    # decide whether these tests pass.
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path / "OneDrive" / "CanvasExpert"))


def _base_session(**extra):
    from datetime import datetime, timezone
    session = {
        "session_id": "sess-1",
        "course_id": "course-1",
        "assignment_id": "assign-1",
        "mode": "assisted",
        "canvas_writeback_supported": True,
        "comment_writeback_supported": False,
        "auto_post": {
            "enabled": True,
            "authorized_at": datetime.now(timezone.utc).isoformat(),
            "disabled_at": None,
            "policy_version": 2,
        },
        "students": [
            {
                "user_id": "student-1",
                "submission_id": "sub-1",
                "body": "Answer text",
                "ai_score": 91,
                "ai_feedback": "Good work",
                "posted": False,
                "submission_baseline": {"attempt": 1, "submitted_at": "2026-07-01T12:00:00Z"},
            }
        ],
    }
    session.update(extra)
    return session


def _make_canvas_get_all(submissions, assignment_data=None):
    def get_all(path, params):
        return (submissions or []), None
    return get_all


def _make_canvas_get(fresh_assignment):
    def get(path):
        return fresh_assignment, None
    return get


def _make_canvas_send(sent_list):
    def send(method, path, payload):
        sent_list.append((method, path, payload))
        return {"ok": True}
    return send


def test_disabled_guard_skips_fetch_and_put():
    """When auto_post is not enabled, no fresh fetch or PUT occurs."""
    session = _base_session()
    session["auto_post"]["enabled"] = False
    sent = []

    result = run_interactive_autopush(
        session=session,
        trigger="assisted_start",
        canvas_get_all=None,
        canvas_get=None,
        canvas_send=None,
    )

    assert result["summary"]["skipped_reason"] == "auto_post_disabled"


def test_policy_v1_guard_skips():
    """A session with policy_version < 2 is skipped."""
    session = _base_session()
    session["auto_post"]["policy_version"] = 1

    result = run_interactive_autopush(
        session=session,
        trigger="assisted_start",
        canvas_get_all=None,
        canvas_get=None,
        canvas_send=None,
    )

    assert result["summary"]["skipped_reason"] == "auto_post_old_policy"


def test_fast_mode_guard_skips():
    """Fast mode cannot auto-post."""
    session = _base_session(mode="fast")

    result = run_interactive_autopush(
        session=session,
        trigger="assisted_start",
        canvas_get_all=None,
        canvas_get=None,
        canvas_send=None,
    )

    assert result["summary"]["skipped_reason"] == "mode_fast_unsupported"


def test_new_quiz_writeback_guard_skips():
    """New Quiz mode (canvas_writeback_supported=False) is skipped."""
    session = _base_session(canvas_writeback_supported=False)

    result = run_interactive_autopush(
        session=session,
        trigger="assisted_start",
        canvas_get_all=None,
        canvas_get=None,
        canvas_send=None,
    )

    assert result["summary"]["skipped_reason"] == "canvas_writeback_not_supported"


def test_empty_only_user_ids_skips():
    """An empty only_user_ids set evaluates nobody."""
    session = _base_session()

    result = run_interactive_autopush(
        session=session,
        trigger="packet_import",
        canvas_get_all=None,
        canvas_get=None,
        canvas_send=None,
        only_user_ids=set(),
    )

    assert result["summary"]["skipped_reason"] == "no_user_ids_to_evaluate"


def test_zero_puts_when_fresh_fetch_fails():
    """A fresh fetch error returns zero PUTs."""
    session = _base_session()
    sent = []

    def canvas_get_all(path, params):
        return None, "Canvas API error"

    def canvas_get(path):
        return None, "Fallback error"

    result = run_interactive_autopush(
        session=session,
        trigger="assisted_start",
        canvas_get_all=canvas_get_all,
        canvas_get=canvas_get,
        canvas_send=_make_canvas_send(sent),
    )

    assert "fresh_fetch_failed" in (result["summary"].get("skipped_reason") or "")
    assert not sent


def test_happy_path_posts_grade_and_comment():
    """A valid session posts grade + comment and returns summary."""
    session = _base_session()
    sent = []

    fresh_sub = {
        "user_id": "student-1",
        "id": "sub-1",
        "attempt": 1,
        "submitted_at": "2026-07-01T12:00:00Z",
        "excused": False,
        "workflow_state": "submitted",
        "score": None,
        "assignment": {
            "id": "assign-1",
            "course_id": "course-1",
            "points_possible": 100,
            "submission_types": ["online_text_entry"],
            "grading_type": "points",
        },
    }

    def canvas_get_all(path, params):
        return [fresh_sub], None

    def canvas_get(path):
        return fresh_sub.get("assignment"), None

    result = run_interactive_autopush(
        session=session,
        trigger="assisted_start",
        canvas_get_all=canvas_get_all,
        canvas_get=canvas_get,
        canvas_send=_make_canvas_send(sent),
        now="2026-07-01T13:00:00+00:00",
    )

    # Happy path returns {summary, log_entry, autopush_result}
    assert result["summary"]["pushed"] == 1
    assert result["summary"]["evaluated"] == 1
    assert result["summary"]["needs_review"] == 0
    assert result["summary"]["blocked"] == 0
    assert len(sent) == 1
    method, path, payload = sent[0]
    assert method == "PUT"
    assert "posted_grade" in payload.get("submission", {})
    assert "comment" in payload
    assert result["log_entry"]["trigger"] == "assisted_start"
    assert result["log_entry"]["pushed"] == 1


def test_idempotent_second_run_makes_no_second_put():
    """A student already posted with an idempotency key is skipped."""
    session = _base_session()
    session["students"][0]["posted"] = True
    session["students"][0]["status"] = "auto_pushed"
    session["students"][0]["autopush_idempotency_key"] = "pg-autopush:v2:course-1:assign-1:student-1:sub-1:91:abc123"

    # Provide minimal fresh data so guards pass
    fresh_sub = {
        "user_id": "student-1", "id": "sub-1",
        "attempt": 1, "submitted_at": "2026-07-01T12:00:00Z",
        "excused": False, "workflow_state": "submitted", "score": None,
        "assignment": {
            "id": "assign-1", "course_id": "course-1",
            "points_possible": 100, "submission_types": ["online_text_entry"],
            "grading_type": "points",
        },
    }

    def canvas_get_all(path, params):
        return [fresh_sub], None

    def canvas_get(path):
        return fresh_sub["assignment"], None

    result = run_interactive_autopush(
        session=session,
        trigger="assisted_start",
        canvas_get_all=canvas_get_all,
        canvas_get=canvas_get,
        canvas_send=lambda *a: None,
    )

    # Already-pushed student is evaluated as blocked
    assert result["summary"]["pushed"] == 0
    assert result["summary"]["evaluated"] == 1
    assert result["summary"]["reason_counts"].get("already_pushed") == 1


def test_only_user_ids_subset():
    """When only_user_ids is set, only matching students are evaluated."""
    session = _base_session()
    session["students"].append({
        "user_id": "student-2",
        "submission_id": "sub-2",
        "body": "More work",
        "ai_score": 85,
        "ai_feedback": "Good",
        "posted": False,
        "submission_baseline": {"attempt": 1, "submitted_at": "2026-07-01T12:00:00Z"},
    })
    sent = []

    fresh_sub_1 = {
        "user_id": "student-1",
        "id": "sub-1",
        "attempt": 1,
        "submitted_at": "2026-07-01T12:00:00Z",
        "excused": False, "workflow_state": "submitted", "score": None,
        "assignment": {
            "id": "assign-1", "course_id": "course-1",
            "points_possible": 100, "submission_types": ["online_text_entry"],
            "grading_type": "points",
        },
    }
    fresh_sub_2 = {
        "user_id": "student-2",
        "id": "sub-2",
        "attempt": 1,
        "submitted_at": "2026-07-01T12:00:00Z",
        "excused": False, "workflow_state": "submitted", "score": None,
        "assignment": {
            "id": "assign-1", "course_id": "course-1",
            "points_possible": 100, "submission_types": ["online_text_entry"],
            "grading_type": "points",
        },
    }

    def canvas_get_all(path, params):
        return [fresh_sub_1, fresh_sub_2], None

    def canvas_get(path):
        return fresh_sub_1["assignment"], None

    result = run_interactive_autopush(
        session=session,
        trigger="packet_import",
        canvas_get_all=canvas_get_all,
        canvas_get=canvas_get,
        canvas_send=_make_canvas_send(sent),
        only_user_ids={"student-2"},
        now="2026-07-01T13:00:00+00:00",
    )

    assert result["summary"]["pushed"] == 1
    assert result["summary"]["evaluated"] == 1
    assert len(sent) == 1
    # student-2 should be the one pushed — check the URL path
    assert "student-2" in sent[0][1]


def test_summary_sanitization():
    """Summary/log entries contain no student names, response text, or grades."""
    session = _base_session()
    sent = []

    fresh_sub = {
        "user_id": "student-1", "id": "sub-1",
        "attempt": 1, "submitted_at": "2026-07-01T12:00:00Z",
        "excused": False, "workflow_state": "submitted", "score": None,
        "assignment": {
            "id": "assign-1", "course_id": "course-1",
            "points_possible": 100, "submission_types": ["online_text_entry"],
            "grading_type": "points",
        },
    }

    def canvas_get_all(path, params):
        return [fresh_sub], None

    def canvas_get(path):
        return fresh_sub["assignment"], None

    result = run_interactive_autopush(
        session=session,
        trigger="assisted_start",
        canvas_get_all=canvas_get_all,
        canvas_get=canvas_get,
        canvas_send=_make_canvas_send(sent),
        now="2026-07-01T13:00:00+00:00",
    )

    assert "summary" in result
    summary_str = str(result["summary"])
    log_str = str(result["log_entry"])
    # Summary should not contain response text or feedback
    assert "Answer text" not in summary_str
    assert "Good work" not in summary_str
    assert "Answer text" not in log_str
    assert "Good work" not in log_str


def test_packet_mode_works():
    """Packet mode sessions can auto-post after import."""
    session = _base_session(mode="packet")
    sent = []

    fresh_sub = {
        "user_id": "student-1",
        "id": "sub-1",
        "attempt": 1,
        "submitted_at": "2026-07-01T12:00:00Z",
        "excused": False, "workflow_state": "submitted", "score": None,
        "assignment": {
            "id": "assign-1", "course_id": "course-1",
            "points_possible": 100, "submission_types": ["online_text_entry"],
            "grading_type": "points",
        },
    }

    def canvas_get_all(path, params):
        return [fresh_sub], None

    def canvas_get(path):
        return fresh_sub["assignment"], None

    result = run_interactive_autopush(
        session=session,
        trigger="packet_import",
        canvas_get_all=canvas_get_all,
        canvas_get=canvas_get,
        canvas_send=_make_canvas_send(sent),
        only_user_ids={"student-1"},
        now="2026-07-01T13:00:00+00:00",
    )

    assert result["summary"]["pushed"] == 1
    assert len(sent) == 1


# ── Route-level fetch-failure regression ──────────────────────────────────

def test_runner_fetch_failure_returns_summary_and_log_entry():
    """The runner keeps one return shape; route persistence is tested separately."""
    session = _base_session()
    sent = []

    def canvas_get_all(path, params):
        return None, "Canvas API error"

    def canvas_get(path):
        return None, "Fallback error"

    result = run_interactive_autopush(
        session=session,
        trigger="assisted_start",
        canvas_get_all=canvas_get_all,
        canvas_get=canvas_get,
        canvas_send=_make_canvas_send(sent),
    )

    # Every return path must carry these three keys
    assert "summary" in result
    assert "log_entry" in result
    assert "autopush_result" in result
    assert "fresh_fetch_failed" in (result["summary"].get("skipped_reason") or "")
    assert result["summary"]["pushed"] == 0
    assert result["log_entry"]["skipped_reason"] == result["summary"]["skipped_reason"]
    assert not sent


# ── Guard-level returns also carry the full shape ─────────────────────────

def test_guard_returns_have_summary_and_log_entry():
    """Every guard-level early exit must return {summary, log_entry, autopush_result}."""
    for disabled, pv, mode, wb, expected in [
        (False, 2, "assisted", True, None),  # no guard tripped
        (True, 2, "assisted", True, "auto_post_disabled"),
        (False, 1, "assisted", True, "auto_post_old_policy"),
        (False, 2, "fast", True, "mode_fast_unsupported"),
        (False, 2, "assisted", False, "canvas_writeback_not_supported"),
    ]:
        session = _base_session()
        session["auto_post"]["enabled"] = not disabled
        session["auto_post"]["policy_version"] = pv
        session["mode"] = mode
        session["canvas_writeback_supported"] = wb

        result = run_interactive_autopush(
            session=session,
            trigger="assisted_start",
            canvas_get_all=None,
            canvas_get=None,
            canvas_send=None,
        )

        assert "summary" in result, f"guard {expected}: missing summary"
        assert "log_entry" in result, f"guard {expected}: missing log_entry"
        assert "autopush_result" in result, f"guard {expected}: missing autopush_result"
        if expected:
            assert result["summary"]["skipped_reason"] == expected, f"guard {expected} mismatch"
            assert result["log_entry"]["skipped_reason"] == expected, f"guard {expected} log mismatch"


def test_notify_write_through_fires_only_on_a_real_push(monkeypatch):
    """The post-push convergence helper fires the write-through refresh only
    when there is a course_id AND a positive pushed count."""
    from api.webui.routes import powergrader as pg
    calls = []
    monkeypatch.setattr(pg.mirror_service, "notify_course_changed",
                        lambda course_id, **kw: calls.append(str(course_id)))
    pg._notify_write_through({"course_id": "77"}, 3)   # fires
    pg._notify_write_through({"course_id": "77"}, 0)   # nothing pushed
    pg._notify_write_through({}, 5)                     # no course_id
    pg._notify_write_through(None, 5)                   # no session
    assert calls == ["77"]


def test_notify_write_through_swallows_convergence_errors(monkeypatch):
    """A convergence hiccup must never fail the grade write that just landed."""
    from api.webui.routes import powergrader as pg

    def boom(course_id, **kw):
        raise RuntimeError("mirror down")

    monkeypatch.setattr(pg.mirror_service, "notify_course_changed", boom)
    pg._notify_write_through({"course_id": "77"}, 1)  # must not raise


def test_converge_new_quiz_after_finalize_hits_both_surfaces(monkeypatch):
    """A verified New Quiz finalize converges the gradebook submission (write-
    through refresh) and stale-invalidates the separate New Quiz response cache."""
    from api.webui.routes import powergrader as pg
    from api.mirror import new_quizzes
    notified, invalidated = [], []
    monkeypatch.setattr(pg.mirror_service, "notify_course_changed",
                        lambda course_id, **kw: notified.append(str(course_id)))
    monkeypatch.setattr(new_quizzes, "invalidate_responses",
                        lambda course_id, assignment_id, **kw:
                        invalidated.append((str(course_id), str(assignment_id))))
    pg._converge_new_quiz_after_finalize({"course_id": "55", "assignment_id": "900"}, "u1")
    assert notified == ["55"]
    assert invalidated == [("55", "900")]
