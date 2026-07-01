from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.powergrader.autopush_policy import evaluate_student_for_autopush, make_idempotency_key


def _base_job(**extra):
    job = {
        "course_id": "course-1",
        "assignment_id": "assign-1",
        "status": "session_ready",
        "auto_push": True,
        "push_policy": {
            "enabled": True,
            "allow_grade_push": True,
            "allow_comment_push": True,
            "policy_version": 1,
        },
        "assignment": {
            "course_id": "course-1",
            "assignment_id": "assign-1",
            "points_possible": 100,
            "submission_types": ["online_text_entry"],
        },
    }
    job.update(extra)
    return job


def _base_student(**extra):
    student = {
        "user_id": "student-1",
        "submission_id": "submission-1",
        "body": "Answer text",
        "ai_score": 91,
        "ai_feedback": "Good work",
    }
    student.update(extra)
    return student


def test_no_opt_in_blocks():
    job = _base_job(auto_push=False)

    result = evaluate_student_for_autopush(
        job=job,
        assignment=job["assignment"],
        student=_base_student(),
    )

    assert result["decision"] == "blocked"
    assert result["blocked_reason"] == "auto_push_not_opted_in"
    assert result["review_needed_reason"] == ""


def test_valid_opted_in_score_and_feedback_allows_auto_push_with_deterministic_key():
    job = _base_job()
    student = _base_student(ai_score=93, ai_feedback="Clear reasoning")

    first = evaluate_student_for_autopush(
        job=job,
        assignment=job["assignment"],
        student=student,
    )
    second = evaluate_student_for_autopush(
        job=job,
        assignment=job["assignment"],
        student=student,
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
        policy_version=1,
    )


def test_score_out_of_bounds_blocks():
    job = _base_job()
    student = _base_student(ai_score=101)

    result = evaluate_student_for_autopush(
        job=job,
        assignment=job["assignment"],
        student=student,
    )

    assert result["decision"] == "blocked"
    assert result["blocked_reason"] == "score_out_of_bounds"


def test_missing_feedback_blocks_when_comments_are_enabled():
    job = _base_job()
    student = _base_student(ai_feedback="")

    result = evaluate_student_for_autopush(
        job=job,
        assignment=job["assignment"],
        student=student,
    )

    assert result["decision"] == "blocked"
    assert result["blocked_reason"] == "missing_ai_feedback"


def test_existing_canvas_work_or_submission_change_routes_to_review():
    job = _base_job()
    student = _base_student()

    existing = evaluate_student_for_autopush(
        job=job,
        assignment=job["assignment"],
        student=student,
        canvas_state={
            "existing_score": 88,
            "existing_comments": ["Teacher note"],
        },
    )
    changed = evaluate_student_for_autopush(
        job=job,
        assignment=job["assignment"],
        student=student,
        canvas_state={
            "submission_changed": True,
        },
    )

    assert existing["decision"] == "needs_review"
    assert existing["review_needed_reason"] == "existing_canvas_work_detected"
    assert changed["decision"] == "needs_review"
    assert changed["review_needed_reason"] == "submission_changed"


def test_matching_previous_receipt_blocks_as_already_pushed():
    job = _base_job()
    student = _base_student()
    expected_key = make_idempotency_key(
        course_id="course-1",
        assignment_id="assign-1",
        user_id="student-1",
        submission_id="submission-1",
        score="91",
        feedback="Good work",
        policy_version=1,
    )

    result = evaluate_student_for_autopush(
        job=job,
        assignment=job["assignment"],
        student=student,
        canvas_state={
            "last_receipt": {"idempotency_key": expected_key},
        },
    )

    assert result["decision"] == "blocked"
    assert result["blocked_reason"] == "already_pushed"
    assert result["idempotency_key"] == expected_key


def test_idempotency_conflict_blocks():
    job = _base_job()
    student = _base_student()

    result = evaluate_student_for_autopush(
        job=job,
        assignment=job["assignment"],
        student=student,
        canvas_state={
            "idempotency_conflict": True,
        },
    )

    assert result["decision"] == "blocked"
    assert result["blocked_reason"] == "idempotency_conflict"


def test_grade_only_policy_allows_empty_feedback_when_comments_disabled():
    job = _base_job(
        push_policy={
            "enabled": True,
            "allow_grade_push": True,
            "allow_comment_push": False,
            "policy_version": 1,
        }
    )
    student = _base_student(ai_feedback="")

    result = evaluate_student_for_autopush(
        job=job,
        assignment=job["assignment"],
        student=student,
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
        policy_version=1,
    )
