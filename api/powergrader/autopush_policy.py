"""Pure policy checks for PowerGrader auto-push decisions.

This module does not talk to Canvas or mutate queue files. It only evaluates a
context/student snapshot and returns a structured decision payload.
"""
from __future__ import annotations

import hashlib
from decimal import Decimal, InvalidOperation

from .autoscore_queue import classify_assignment_for_autoscore
from . import autopush_policy_result as policy_result

POLICY_VERSION = 2
ALLOWED_DECISIONS = {"auto_push_allowed", "needs_review", "blocked"}
READY_CONTEXT_STATUSES = {"session_ready", "push_ready", "auto_pushing", "partial_auto_pushed"}


def _mapping(value: dict | None) -> dict:
    return value if isinstance(value, dict) else {}


def _text(value) -> str:
    return str(value or "").strip()


def _first_present(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _as_decimal(value):
    text = _text(value)
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _normalize_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return format(normalized.quantize(Decimal(1)), "f")
    return format(normalized, "f").rstrip("0").rstrip(".")


def _hash_feedback(feedback: str) -> str:
    return hashlib.sha256(_text(feedback).encode("utf-8")).hexdigest()


def _effective_job_policy(job: dict) -> dict:
    policy = _mapping(job.get("push_policy"))
    return policy


def _effective_score_feedback(student: dict, ai_result: dict | None):
    source = _mapping(ai_result) if ai_result is not None else _mapping(student)
    score = _first_present(
        source.get("score"),
        source.get("ai_score"),
        source.get("grade"),
        student.get("ai_score"),
        student.get("score"),
    )
    feedback = _first_present(
        source.get("feedback"),
        source.get("ai_feedback"),
        source.get("comment"),
        student.get("ai_feedback"),
        student.get("feedback"),
        student.get("comment"),
    )
    return score, _text(feedback)


def _effective_points_possible(job: dict, assignment: dict, ai_result: dict | None, student: dict):
    for source in (
        _mapping(assignment),
        _mapping(job.get("assignment")),
        _mapping(ai_result) if ai_result is not None else {},
        _mapping(student),
    ):
        candidate = _first_present(
            source.get("points_possible"),
            source.get("max_points"),
            source.get("max_score"),
            source.get("ai_max_score"),
            source.get("points_max"),
        )
        points = _as_decimal(candidate)
        if points is not None:
            return points
    return None


def _student_identity(student: dict, ai_result: dict | None, canvas_state: dict | None):
    student_map = _mapping(student)
    ai_map = _mapping(ai_result) if ai_result is not None else {}
    canvas_map = _mapping(canvas_state)
    user_id = _first_present(student_map.get("user_id"), ai_map.get("user_id"), canvas_map.get("user_id"))
    submission_id = _first_present(
        student_map.get("submission_id"),
        ai_map.get("submission_id"),
        canvas_map.get("submission_id"),
    )
    return _text(user_id), _text(submission_id)


def _submission_has_work(student: dict) -> bool:
    student_map = _mapping(student)
    for key in ("body", "submission_text", "text", "content"):
        if _text(student_map.get(key)):
            return True
    for key in ("attachments", "code_files"):
        value = student_map.get(key)
        if isinstance(value, list) and value:
            return True
        if isinstance(value, tuple) and len(value):
            return True
    return False


def _has_error_blob(value: dict | None) -> bool:
    mapping = _mapping(value)
    if not mapping:
        return False
    for key in ("privacy_error", "scoring_error", "ai_scoring_error", "error"):
        item = mapping.get(key)
        if item not in (None, "", False):
            return True
    status = _text(mapping.get("status")).lower()
    if status in {"error", "failed", "blocked"}:
        return True
    return False


def make_idempotency_key(
    *,
    course_id,
    assignment_id,
    user_id=None,
    submission_id=None,
    score=None,
    feedback: str = "",
    policy_version: int = POLICY_VERSION,
) -> str:
    feedback_hash = _hash_feedback(feedback)
    score_text = _text(score)
    return (
        f"pg-autopush:v{int(policy_version)}:"
        f"{_text(course_id)}:{_text(assignment_id)}:"
        f"{_text(user_id)}:{_text(submission_id)}:"
        f"{score_text}:{feedback_hash}"
    )


def _canvas_last_receipt_key(canvas_state: dict | None) -> str:
    receipt = _mapping((_mapping(canvas_state)).get("last_receipt"))
    return _text(receipt.get("idempotency_key"))


def _has_existing_canvas_work(canvas_state: dict | None) -> bool:
    canvas_map = _mapping(canvas_state)
    if canvas_map.get("existing_score") not in (None, ""):
        return True
    existing_comments = canvas_map.get("existing_comments")
    if isinstance(existing_comments, list):
        return bool(existing_comments)
    return _text(existing_comments) != ""


def _policy_warning_reason(canvas_state: dict | None) -> str:
    canvas_map = _mapping(canvas_state)
    warnings = canvas_map.get("policy_warnings")
    if isinstance(warnings, list):
        warnings = [str(item).strip() for item in warnings if str(item).strip()]
        if warnings:
            return warnings[0]
    elif _text(warnings):
        return _text(warnings)
    return ""


def evaluate_student_for_autopush(
    *,
    context: dict,
    assignment: dict,
    student: dict,
    ai_result: dict | None = None,
    canvas_state: dict | None = None,
) -> dict:
    context_map = _mapping(context)
    assignment_map = _mapping(assignment)
    student_map = _mapping(student)
    ai_map = _mapping(ai_result) if ai_result is not None else {}
    canvas_map = _mapping(canvas_state)
    policy = _effective_job_policy(context_map)

    policy_checks = policy_result.empty_policy_checks()

    context_auto_push = context_map.get("auto_push") is True
    policy_enabled = policy.get("enabled") is True
    policy_checks["teacher_opt_in"] = context_auto_push
    policy_checks["policy_enabled"] = policy_enabled
    if not context_auto_push or not policy_enabled:
        return policy_result.blocked(policy_checks=policy_checks, blocked_reason="auto_push_not_opted_in")

    allow_grade_push = policy.get("allow_grade_push")
    if allow_grade_push is None:
        allow_grade_push = True
    allow_comment_push = policy.get("allow_comment_push")
    if allow_comment_push is None:
        allow_comment_push = True
    policy_checks["grade_push_allowed"] = bool(allow_grade_push)
    policy_checks["comments_allowed"] = bool(allow_comment_push)

    context_status = _text(context_map.get("status"))
    if context_status and context_status not in READY_CONTEXT_STATUSES:
        policy_checks["context_status_allowed"] = False
        return policy_result.blocked(policy_checks=policy_checks, blocked_reason="context_not_ready_for_push")
    policy_checks["context_status_allowed"] = True

    eligibility_source = assignment_map if assignment_map else _mapping(context_map.get("assignment_snapshot"))
    eligibility, eligibility_reason = classify_assignment_for_autoscore(eligibility_source)
    if eligibility == "unsupported":
        return policy_result.blocked(policy_checks=policy_checks, blocked_reason="assignment_unsupported")
    if eligibility != "eligible":
        policy_checks["assignment_supported"] = False
        return policy_result.needs_review(policy_checks=policy_checks, review_needed_reason="mixed_submission_type")
    policy_checks["assignment_supported"] = True

    user_id, submission_id = _student_identity(student_map, ai_map if ai_result is not None else None, canvas_map)
    if not user_id and not submission_id:
        return policy_result.blocked(policy_checks=policy_checks, blocked_reason="missing_context_identity")

    if not _submission_has_work(student_map):
        policy_checks["submission_present"] = False
        return policy_result.blocked(policy_checks=policy_checks, blocked_reason="missing_submitted_work")
    policy_checks["submission_present"] = True

    if _has_error_blob(student_map) or _has_error_blob(ai_map) or _has_error_blob(canvas_map):
        return policy_result.blocked(policy_checks=policy_checks, blocked_reason="privacy_or_scoring_error")

    # --- Fail-closed fresh-state checks ---
    canvas_state_present = canvas_map.get("canvas_state_present")
    if canvas_state_present is False:
        return policy_result.blocked(policy_checks=policy_checks, blocked_reason="canvas_state_unavailable")
    if canvas_state_present is not True:
        return policy_result.needs_review(policy_checks=policy_checks, review_needed_reason="canvas_state_incomplete")

    if canvas_map.get("excused") is True:
        return policy_result.blocked(policy_checks=policy_checks, blocked_reason="submission_excused")

    workflow_state = _text(canvas_map.get("workflow_state"))
    if workflow_state == "unsubmitted":
        return policy_result.blocked(policy_checks=policy_checks, blocked_reason="submission_not_submitted")
    if not workflow_state:
        return policy_result.needs_review(policy_checks=policy_checks, review_needed_reason="canvas_state_incomplete")

    # --- Submission identity / drift checks ---
    baseline = _mapping(student_map.get("submission_baseline"))
    fresh_attempt = canvas_map.get("attempt")
    fresh_submitted_at = canvas_map.get("submitted_at")
    baseline_attempt = baseline.get("attempt")
    baseline_submitted_at = baseline.get("submitted_at")

    if baseline_attempt is None and baseline_submitted_at is None:
        # No baseline available — existing session created before this field
        return policy_result.needs_review(policy_checks=policy_checks, review_needed_reason="submission_identity_unavailable")
    if fresh_attempt is None or fresh_submitted_at is None:
        return policy_result.needs_review(policy_checks=policy_checks, review_needed_reason="submission_identity_unavailable")
    if str(baseline_attempt) != str(fresh_attempt) or str(baseline_submitted_at) != str(fresh_submitted_at):
        return policy_result.needs_review(policy_checks=policy_checks, review_needed_reason="submission_changed")

    # --- Existing Canvas work clearance ---
    score_value, feedback_value = _effective_score_feedback(student_map, ai_result)
    score = _as_decimal(score_value)
    if score is None:
        return policy_result.blocked(policy_checks=policy_checks, blocked_reason="missing_ai_score")
    policy_checks["score_present"] = True

    points_possible = _effective_points_possible(context_map, assignment_map, ai_result, student_map)
    if points_possible is None:
        return policy_result.blocked(policy_checks=policy_checks, blocked_reason="missing_points_possible")

    if score < Decimal("0") or score > points_possible:
        return policy_result.blocked(policy_checks=policy_checks, blocked_reason="score_out_of_bounds")
    policy_checks["score_in_range"] = True

    feedback_required = bool(allow_comment_push)
    feedback_text = _text(feedback_value)
    if feedback_required and not feedback_text:
        return policy_result.blocked(policy_checks=policy_checks, blocked_reason="missing_ai_feedback")
    policy_checks["feedback_present"] = bool(feedback_text)

    course_id = _first_present(context_map.get("course_id"), assignment_map.get("course_id"))
    assignment_id = _first_present(context_map.get("assignment_id"), assignment_map.get("id"))
    if course_id in (None, "") or assignment_id in (None, ""):
        return policy_result.blocked(policy_checks=policy_checks, blocked_reason="missing_context_identity")

    score_key = _normalize_decimal(score)
    idempotency_key = make_idempotency_key(
        course_id=course_id,
        assignment_id=assignment_id,
        user_id=user_id,
        submission_id=submission_id,
        score=score_key,
        feedback=feedback_text if allow_comment_push else "",
        policy_version=policy.get("policy_version", POLICY_VERSION),
    )

    last_receipt_key = _canvas_last_receipt_key(canvas_map)
    if canvas_map.get("idempotency_conflict") is True:
        policy_checks["idempotency_clear"] = False
        return policy_result.blocked(policy_checks=policy_checks, blocked_reason="idempotency_conflict", idempotency_key=idempotency_key)
    if last_receipt_key and last_receipt_key == idempotency_key:
        policy_checks["idempotency_clear"] = False
        return policy_result.blocked(policy_checks=policy_checks, blocked_reason="already_pushed", idempotency_key=idempotency_key)

    if canvas_map.get("submission_changed") is True:
        return policy_result.needs_review(policy_checks=policy_checks, review_needed_reason="submission_changed", idempotency_key=idempotency_key)

    warning_reason = _policy_warning_reason(canvas_map)
    if warning_reason:
        return policy_result.needs_review(policy_checks=policy_checks, review_needed_reason=warning_reason, idempotency_key=idempotency_key)

    if _has_existing_canvas_work(canvas_map):
        return policy_result.needs_review(policy_checks=policy_checks, review_needed_reason="existing_canvas_work_detected", idempotency_key=idempotency_key)

    policy_checks["idempotency_clear"] = True
    policy_checks["canvas_state_clear"] = True

    if allow_grade_push is False and allow_comment_push is False:
        return policy_result.blocked(policy_checks=policy_checks, blocked_reason="push_policy_disabled", idempotency_key=idempotency_key)

    return policy_result.auto_push_allowed(policy_checks=policy_checks, idempotency_key=idempotency_key)
