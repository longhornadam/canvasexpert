"""Decision payload helpers for scheduled PowerGrader auto-push policy."""

from __future__ import annotations


def empty_policy_checks() -> dict:
    return {
        "teacher_opt_in": False,
        "policy_enabled": False,
        "job_status_allowed": False,
        "assignment_supported": False,
        "submission_present": False,
        "score_present": False,
        "score_in_range": False,
        "grade_push_allowed": False,
        "comments_allowed": False,
        "feedback_present": False,
        "idempotency_clear": False,
        "canvas_state_clear": False,
    }


def decision_payload(
    *,
    decision: str,
    policy_checks: dict,
    idempotency_key: str = "",
    review_needed_reason: str = "",
    blocked_reason: str = "",
) -> dict:
    return {
        "decision": decision,
        "review_needed_reason": review_needed_reason,
        "blocked_reason": blocked_reason,
        "policy_checks": policy_checks,
        "idempotency_key": idempotency_key,
    }


def blocked(*, policy_checks: dict, blocked_reason: str, idempotency_key: str = "") -> dict:
    return decision_payload(
        decision="blocked",
        policy_checks=policy_checks,
        idempotency_key=idempotency_key,
        blocked_reason=blocked_reason,
    )


def needs_review(*, policy_checks: dict, review_needed_reason: str, idempotency_key: str = "") -> dict:
    return decision_payload(
        decision="needs_review",
        policy_checks=policy_checks,
        idempotency_key=idempotency_key,
        review_needed_reason=review_needed_reason,
    )


def auto_push_allowed(*, policy_checks: dict, idempotency_key: str) -> dict:
    return decision_payload(
        decision="auto_push_allowed",
        policy_checks=policy_checks,
        idempotency_key=idempotency_key,
    )