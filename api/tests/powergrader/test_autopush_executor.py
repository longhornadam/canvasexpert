from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.powergrader.autopush_executor import run_autopush_for_session


def _base_context(**extra):
    ctx = {
        "course_id": "course-1",
        "assignment_id": "assign-1",
        "status": "session_ready",
        "auto_push": True,
        "push_policy": {
            "enabled": True,
            "allow_grade_push": True,
            "allow_comment_push": True,
            "policy_version": 2,
        },
        "source": "scheduled",
        "session_id": "session-1",
        "grade_push_allowed": True,
        "comment_push_allowed": True,
    }
    ctx.update(extra)
    return ctx


def _base_assignment(**extra):
    assignment = {
        "id": "assign-1",
        "course_id": "course-1",
        "points_possible": 100,
        "submission_types": ["online_text_entry"],
        "grading_type": "points",
    }
    assignment.update(extra)
    return assignment


def _base_student(**extra):
    student = {
        "user_id": "student-1",
        "submission_id": "sub-1",
        "body": "Student work",
        "ai_score": 93,
        "ai_feedback": "Strong answer",
        "posted": False,
        "submission_baseline": {
            "attempt": 1,
            "submitted_at": "2026-07-01T12:00:00Z",
        },
    }
    student.update(extra)
    return student


def _base_canvas_state(**extra):
    state = {
        "canvas_state_present": True,
        "user_id": "student-1",
        "submission_id": "sub-1",
        "attempt": 1,
        "submitted_at": "2026-07-01T12:00:00Z",
        "excused": False,
        "workflow_state": "submitted",
    }
    state.update(extra)
    return state


def test_pushes_only_allowed_student_and_writes_grade_comment_payload_and_receipt(tmp_path):
    ctx = _base_context()
    session = {
        "students": [
            _base_student(),
            _base_student(user_id="student-2", submission_id="sub-2", ai_score=88, ai_feedback="Needs review", body="Student work 2"),
        ]
    }
    assignment = _base_assignment()
    sent = []

    def canvas_send(method, path, payload):
        sent.append((method, path, payload))
        return {"ok": True}

    result = run_autopush_for_session(
        context=ctx,
        session=session,
        assignment=assignment,
        canvas_states_by_user={
            "student-1": _base_canvas_state(),
            "student-2": _base_canvas_state(user_id="student-2", submission_id="sub-2", existing_score=75),
        },
        canvas_send=canvas_send,
        receipt_dir=str(tmp_path),
        now="2026-07-01T12:00:00+00:00",
    )

    assert result["ok"] is True
    assert result["pushed"] == 1
    assert result["needs_review"] == 1
    assert result["blocked"] == 0
    assert len(sent) == 1
    method, path, payload = sent[0]
    assert method == "PUT"
    assert path == "/api/v1/courses/course-1/assignments/assign-1/submissions/student-1"
    assert payload["submission"]["posted_grade"] == "93"
    # Auto-post writes with no teacher review, so the assistant's words carry
    # the attribution before they ever reach a student.
    assert payload["comment"]["text_comment"] == (
        "Autofeedback from an automated assistant:\n\nStrong answer"
    )
    assert session["students"][0]["posted"] is True
    assert session["students"][0]["status"] == "auto_pushed"
    assert session["students"][0]["autopush_idempotency_key"]
    assert session["students"][0]["autopush_receipt_id"]
    assert session["students"][1]["posted"] is False
    assert session["students"][1].get("status") != "auto_pushed"
    assert len(result["receipts"]) == 1
    receipt = result["receipts"][0]
    assert receipt["pushed_fields"] == {"grade": True, "comment": True}
    receipt_path = Path(receipt["receipt_path"])
    assert receipt_path.exists()
    on_disk = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert on_disk["user_id"] == "student-1"
    assert on_disk["canvas_path"] == path
    assert on_disk["idempotency_key"] == receipt["idempotency_key"]


def test_needs_review_and_blocked_students_are_skipped_and_not_posted(tmp_path):
    ctx = _base_context()
    session = {
        "students": [
            _base_student(user_id="student-1", submission_id="sub-1", ai_score=101, ai_feedback="Too high"),
            _base_student(user_id="student-2", submission_id="sub-2", ai_score=88, ai_feedback="Looks fine", body="Student work"),
        ]
    }
    assignment = _base_assignment()
    sent = []

    def canvas_send(method, path, payload):
        sent.append((method, path, payload))
        return {"ok": True}

    result = run_autopush_for_session(
        context=ctx,
        session=session,
        assignment=assignment,
        canvas_states_by_user={
            "student-1": _base_canvas_state(user_id="student-1", submission_id="sub-1"),
            "student-2": _base_canvas_state(user_id="student-2", submission_id="sub-2", existing_score=77),
        },
        canvas_send=canvas_send,
        receipt_dir=str(tmp_path),
    )

    assert result["pushed"] == 0
    assert result["needs_review"] == 1
    assert result["blocked"] == 1
    assert sent == []
    assert session["students"][0]["posted"] is False
    assert session["students"][1]["posted"] is False


def test_matching_existing_session_idempotency_key_skips_canvas_send(tmp_path):
    ctx = _base_context()
    student = _base_student(posted=True, autopush_idempotency_key="pg-autopush:v2:course-1:assign-1:student-1:sub-1:93:deadbeef")
    session = {"students": [student]}
    sent = []

    def canvas_send(method, path, payload):
        sent.append((method, path, payload))
        return {"ok": True}

    result = run_autopush_for_session(
        context=ctx,
        session=session,
        assignment=_base_assignment(),
        canvas_states_by_user=None,
        canvas_send=canvas_send,
        receipt_dir=str(tmp_path),
    )

    assert result["pushed"] == 0
    assert result["blocked"] == 1
    assert result["student_results"][0]["reason"] == "already_pushed"
    assert sent == []


def test_canvas_send_error_does_not_mark_posted_or_write_receipt(tmp_path):
    ctx = _base_context()
    session = {"students": [_base_student()]}

    def canvas_send(method, path, payload):
        raise RuntimeError("send failed")

    result = run_autopush_for_session(
        context=ctx,
        session=session,
        assignment=_base_assignment(),
        canvas_states_by_user={"student-1": _base_canvas_state()},
        canvas_send=canvas_send,
        receipt_dir=str(tmp_path),
        now="2026-07-01T12:00:00+00:00",
    )

    assert result["ok"] is False
    assert result["pushed"] == 0
    assert result["blocked"] == 1
    assert session["students"][0]["posted"] is False
    assert not list(Path(tmp_path).glob("*.json"))
    assert result["errors"][0]["reason"] == "canvas_send_error"


def test_canvas_send_tuple_error_does_not_mark_posted_or_write_receipt(tmp_path):
    ctx = _base_context()
    session = {"students": [_base_student()]}

    def canvas_send(method, path, payload):
        return None, "Canvas rejected update"

    result = run_autopush_for_session(
        context=ctx,
        session=session,
        assignment=_base_assignment(),
        canvas_states_by_user={"student-1": _base_canvas_state()},
        canvas_send=canvas_send,
        receipt_dir=str(tmp_path),
        now="2026-07-01T12:00:00+00:00",
    )

    assert result["ok"] is False
    assert result["pushed"] == 0
    assert result["blocked"] == 1
    assert session["students"][0]["posted"] is False
    assert not list(Path(tmp_path).glob("*.json"))
    assert result["errors"][0]["reason"] == "canvas_send_error"


def test_grade_only_policy_pushes_grade_without_comment_and_allows_empty_feedback(tmp_path):
    ctx = _base_context(
        push_policy={
            "enabled": True,
            "allow_grade_push": True,
            "allow_comment_push": False,
            "policy_version": 2,
        },
        comment_push_allowed=False,
    )
    session = {
        "students": [
            _base_student(ai_feedback="", body="Student work"),
        ]
    }
    sent = []

    def canvas_send(method, path, payload):
        sent.append(payload)
        return {"ok": True}

    result = run_autopush_for_session(
        context=ctx,
        session=session,
        assignment=_base_assignment(),
        canvas_states_by_user={"student-1": _base_canvas_state()},
        canvas_send=canvas_send,
        receipt_dir=str(tmp_path),
        now="2026-07-01T12:00:00+00:00",
    )

    assert result["pushed"] == 1
    assert "comment" not in sent[0]
    assert sent[0]["submission"]["posted_grade"] == "93"


def test_receipt_dir_preflight_creates_dir_and_continues(tmp_path):
    ctx = _base_context()
    session = {"students": [_base_student()]}

    sent = []
    def canvas_send(method, path, payload):
        sent.append(payload)
        return {"ok": True}

    result = run_autopush_for_session(
        context=ctx,
        session=session,
        assignment=_base_assignment(),
        canvas_states_by_user={"student-1": _base_canvas_state()},
        canvas_send=canvas_send,
        receipt_dir=str(tmp_path / "receipts"),
        now="2026-07-01T12:00:00+00:00",
    )

    assert result["pushed"] == 1
    assert len(sent) == 1
    assert session["students"][0]["posted"] is True
    assert len(result["receipts"]) == 1


def test_evaluated_and_reason_counts_in_summary(tmp_path):
    ctx = _base_context()
    session = {
        "students": [
            _base_student(),
            _base_student(user_id="student-2", submission_id="sub-2", ai_score=101, ai_feedback="Too high"),
        ]
    }
    sent = []

    def canvas_send(method, path, payload):
        sent.append((method, path, payload))
        return {"ok": True}

    result = run_autopush_for_session(
        context=ctx,
        session=session,
        assignment=_base_assignment(),
        canvas_states_by_user={
            "student-1": _base_canvas_state(),
            "student-2": _base_canvas_state(user_id="student-2", submission_id="sub-2"),
        },
        canvas_send=canvas_send,
        receipt_dir=str(tmp_path),
    )

    assert result["evaluated"] == 2
    assert result["reason_counts"].get("pushed") == 1
    assert result["reason_counts"].get("score_out_of_bounds") == 1


def test_late_catchup_metadata_is_included_in_payload(tmp_path):
    ctx = _base_context()
    session = {
        "students": [
            _base_student(
                late_catchup={
                    "is_late_catchup": True,
                    "seconds_late_override": 86400,
                }
            )
        ]
    }
    sent = []

    def canvas_send(method, path, payload):
        sent.append(payload)
        return {"ok": True}

    run_autopush_for_session(
        context=ctx,
        session=session,
        assignment=_base_assignment(),
        canvas_states_by_user={"student-1": _base_canvas_state()},
        canvas_send=canvas_send,
        receipt_dir=str(tmp_path),
        now="2026-07-01T12:00:00+00:00",
    )

    assert sent[0]["submission"]["late_policy_status"] == "late"
    assert sent[0]["submission"]["seconds_late_override"] == 86400


def test_receipts_do_not_include_real_name_body_or_raw_feedback(tmp_path):
    ctx = _base_context()
    session = {
        "students": [
            _base_student(real_name="Ada Example", body="Raw body text", ai_feedback="Raw feedback text"),
        ]
    }

    def canvas_send(method, path, payload):
        return {"ok": True}

    result = run_autopush_for_session(
        context=ctx,
        session=session,
        assignment=_base_assignment(),
        canvas_states_by_user={"student-1": _base_canvas_state()},
        canvas_send=canvas_send,
        receipt_dir=str(tmp_path),
        now="2026-07-01T12:00:00+00:00",
    )

    receipt_path = Path(result["receipts"][0]["receipt_path"])
    receipt_text = receipt_path.read_text(encoding="utf-8")
    assert "Ada Example" not in receipt_text
    assert "Raw body text" not in receipt_text
    assert "Raw feedback text" not in receipt_text
