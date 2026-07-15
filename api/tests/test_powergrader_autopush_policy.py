from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.powergrader.autopush_policy import evaluate_student_for_autopush, make_idempotency_key


def _base_context(**extra):
    context = {
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
        "assignment_snapshot": {
            "course_id": "course-1",
            "assignment_id": "assign-1",
            "points_possible": 100,
            "submission_types": ["online_text_entry"],
            "grading_type": "points",
        },
    }
    context.update(extra)
    return context


def _base_student(**extra):
    student = {
        "user_id": "student-1",
        "submission_id": "submission-1",
        "body": "Answer text",
        "ai_score": 91,
        "ai_feedback": "Good work",
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
        "submission_id": "submission-1",
        "attempt": 1,
        "submitted_at": "2026-07-01T12:00:00Z",
        "excused": False,
        "workflow_state": "submitted",
    }
    state.update(extra)
    return state


def test_no_opt_in_blocks():
    context = _base_context(auto_push=False)

    result = evaluate_student_for_autopush(
        context=context,
        assignment=context["assignment_snapshot"],
        student=_base_student(),
    )

    assert result["decision"] == "blocked"
    assert result["blocked_reason"] == "auto_push_not_opted_in"
    assert result["review_needed_reason"] == ""


def test_valid_opted_in_score_and_feedback_allows_auto_push_with_deterministic_key():
    context = _base_context()
    student = _base_student(ai_score=93, ai_feedback="Clear reasoning")

    first = evaluate_student_for_autopush(
        context=context,
        assignment=context["assignment_snapshot"],
        student=student,
        canvas_state=_base_canvas_state(),
    )
    second = evaluate_student_for_autopush(
        context=context,
        assignment=context["assignment_snapshot"],
        student=student,
        canvas_state=_base_canvas_state(),
    )

    assert first["decision"] == "auto_push_allowed"
    assert first["blocked_reason"] == ""
    assert first["review_needed_reason"] == ""
    assert first["idempotency_key"] == second["idempotency_key"]
    assert first["idempotency_key"] == make_idempotency_key(
        course_id="course-1",
        assignment_id="assign-1",
        user_id="student-1",
        submission_id="submission-1",
        score="93",
        feedback="Clear reasoning",
        policy_version=2,
    )


def test_score_out_of_bounds_blocks():
    context = _base_context()
    student = _base_student(ai_score=101)

    result = evaluate_student_for_autopush(
        context=context,
        assignment=context["assignment_snapshot"],
        student=student,
        canvas_state=_base_canvas_state(),
    )

    assert result["decision"] == "blocked"
    assert result["blocked_reason"] == "score_out_of_bounds"


def test_missing_feedback_blocks_when_comments_are_enabled():
    context = _base_context()
    student = _base_student(ai_feedback="")

    result = evaluate_student_for_autopush(
        context=context,
        assignment=context["assignment_snapshot"],
        student=student,
        canvas_state=_base_canvas_state(),
    )

    assert result["decision"] == "blocked"
    assert result["blocked_reason"] == "missing_ai_feedback"


def test_existing_canvas_work_or_submission_change_routes_to_review():
    context = _base_context()
    student = _base_student()

    existing = evaluate_student_for_autopush(
        context=context,
        assignment=context["assignment_snapshot"],
        student=student,
        canvas_state=_base_canvas_state(
            existing_score=88,
            existing_comments=["Teacher note"],
        ),
    )
    changed = evaluate_student_for_autopush(
        context=context,
        assignment=context["assignment_snapshot"],
        student=student,
        canvas_state=_base_canvas_state(
            attempt=2,
            submitted_at="2026-07-02T12:00:00Z",
        ),
    )

    assert existing["decision"] == "needs_review"
    assert existing["review_needed_reason"] == "existing_canvas_work_detected"
    assert changed["decision"] == "needs_review"
    assert changed["review_needed_reason"] == "submission_changed"


def test_matching_previous_receipt_blocks_as_already_pushed():
    context = _base_context()
    student = _base_student()
    expected_key = make_idempotency_key(
        course_id="course-1",
        assignment_id="assign-1",
        user_id="student-1",
        submission_id="submission-1",
        score="91",
        feedback="Good work",
        policy_version=2,
    )

    result = evaluate_student_for_autopush(
        context=context,
        assignment=context["assignment_snapshot"],
        student=student,
        canvas_state=_base_canvas_state(
            last_receipt={"idempotency_key": expected_key},
        ),
    )

    assert result["decision"] == "blocked"
    assert result["blocked_reason"] == "already_pushed"
    assert result["idempotency_key"] == expected_key


def test_idempotency_conflict_blocks():
    context = _base_context()
    student = _base_student()

    result = evaluate_student_for_autopush(
        context=context,
        assignment=context["assignment_snapshot"],
        student=student,
        canvas_state=_base_canvas_state(
            idempotency_conflict=True,
        ),
    )

    assert result["decision"] == "blocked"
    assert result["blocked_reason"] == "idempotency_conflict"


def test_grade_only_policy_allows_empty_feedback_when_comments_disabled():
    context = _base_context(
        push_policy={
            "enabled": True,
            "allow_grade_push": True,
            "allow_comment_push": False,
            "policy_version": 2,
        }
    )
    student = _base_student(ai_feedback="")

    result = evaluate_student_for_autopush(
        context=context,
        assignment=context["assignment_snapshot"],
        student=student,
        canvas_state=_base_canvas_state(),
    )

    assert result["decision"] == "auto_push_allowed"
    assert result["blocked_reason"] == ""
    assert result["review_needed_reason"] == ""
    assert result["policy_checks"]["comments_allowed"] is False
    assert result["idempotency_key"] == make_idempotency_key(
        course_id="course-1",
        assignment_id="assign-1",
        user_id="student-1",
        submission_id="submission-1",
        score="91",
        feedback="",
        policy_version=2,
    )


def test_submission_baseline_missing_routes_to_review():
    context = _base_context()
    student = _base_student()
    del student["submission_baseline"]

    result = evaluate_student_for_autopush(
        context=context,
        assignment=context["assignment_snapshot"],
        student=student,
        canvas_state=_base_canvas_state(),
    )

    assert result["decision"] == "needs_review"
    assert result["review_needed_reason"] == "submission_identity_unavailable"


def test_canvas_state_missing_blocks():
    context = _base_context()
    student = _base_student()

    result = evaluate_student_for_autopush(
        context=context,
        assignment=context["assignment_snapshot"],
        student=student,
        canvas_state={"canvas_state_present": False},
    )

    assert result["decision"] == "blocked"
    assert result["blocked_reason"] == "canvas_state_unavailable"


def test_excused_submission_blocks():
    context = _base_context()
    student = _base_student()

    result = evaluate_student_for_autopush(
        context=context,
        assignment=context["assignment_snapshot"],
        student=student,
        canvas_state=_base_canvas_state(excused=True),
    )

    assert result["decision"] == "blocked"
    assert result["blocked_reason"] == "submission_excused"


def test_unsubmitted_blocks():
    context = _base_context()
    student = _base_student()

    result = evaluate_student_for_autopush(
        context=context,
        assignment=context["assignment_snapshot"],
        student=student,
        canvas_state=_base_canvas_state(workflow_state="unsubmitted"),
    )

    assert result["decision"] == "blocked"
    assert result["blocked_reason"] == "submission_not_submitted"


def test_ai_scoring_error_blocks():
    context = _base_context()
    student = _base_student(ai_scoring_error="OpenRouter returned 500")

    result = evaluate_student_for_autopush(
        context=context,
        assignment=context["assignment_snapshot"],
        student=student,
        canvas_state=_base_canvas_state(),
    )

    assert result["decision"] == "blocked"
    assert result["blocked_reason"] == "privacy_or_scoring_error"


def test_submission_changed_via_baseline_drift_routes_to_review():
    context = _base_context()
    student = _base_student(
        submission_baseline={"attempt": 1, "submitted_at": "2026-07-01T12:00:00Z"}
    )

    result = evaluate_student_for_autopush(
        context=context,
        assignment=context["assignment_snapshot"],
        student=student,
        canvas_state=_base_canvas_state(attempt=2, submitted_at="2026-07-02T12:00:00Z"),
    )

    assert result["decision"] == "needs_review"
    assert result["review_needed_reason"] == "submission_changed"


def test_policy_v1_posted_student_idempotency_blocks_via_receipt():
    """A v1 auto-posted student with a matching receipt key is blocked as already_pushed."""
    context = _base_context()
    student = _base_student()
    # This idempotency key would match what was stored in the receipt
    expected_key = make_idempotency_key(
        course_id="course-1",
        assignment_id="assign-1",
        user_id="student-1",
        submission_id="submission-1",
        score="91",
        feedback="Good work",
        policy_version=2,
    )
    result = evaluate_student_for_autopush(
        context=context,
        assignment=context["assignment_snapshot"],
        student=student,
        canvas_state=_base_canvas_state(
            last_receipt={"idempotency_key": expected_key},
        ),
    )
    assert result["decision"] == "blocked"
    assert result["blocked_reason"] == "already_pushed"
