"""Idempotent PowerGrader auto-push execution helpers.

This module evaluates session students with the pure policy helper and sends
Canvas writes only through an injected callback.
"""
from __future__ import annotations

import json
import hashlib
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from .autopush_policy import POLICY_VERSION, evaluate_student_for_autopush
from .late_catchup import apply_lateness_to_submission_payload


def _mapping(value: dict | None) -> dict:
    return value if isinstance(value, dict) else {}


def _text(value) -> str:
    return str(value or "").strip()


def _now_iso(now=None) -> str:
    if now is None:
        current = datetime.now(timezone.utc)
    elif isinstance(now, datetime):
        current = now
    else:
        current = datetime.fromisoformat(str(now).replace("Z", "+00:00"))
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.replace(microsecond=0).isoformat()


def _student_rows(session: dict) -> list[dict]:
    students = (session or {}).get("students")
    if not isinstance(students, list):
        return []
    return students


def _student_user_id(student: dict) -> str:
    return _text(student.get("user_id"))


def _student_submission_id(student: dict, canvas_state: dict | None = None) -> str:
    canvas_map = _mapping(canvas_state)
    return _text(
        student.get("submission_id")
        or canvas_map.get("submission_id")
        or student.get("id")
    )


def _feedback_present(student: dict, ai_result: dict | None) -> bool:
    source = _mapping(ai_result) if ai_result is not None else _mapping(student)
    for key in ("feedback", "ai_feedback", "comment"):
        if _text(source.get(key)):
            return True
    return False


def _build_canvas_payload(context: dict, assignment: dict, student: dict, decision: dict) -> dict:
    # Single grading surface: the AI-feedback comment written below is
    # PowerGrader's alone. Gradebook adjusts grades, never feedback.
    # See docs/handoffs/fold-feedbackexpert-into-powergrader.md.
    allow_grade_push = context.get("grade_push_allowed", True)
    allow_comment_push = context.get("comment_push_allowed", True)

    ai_result = {
        "score": student.get("ai_score"),
        "feedback": student.get("ai_feedback"),
    }
    payload = {"submission": {}}
    if allow_grade_push:
        payload["submission"]["posted_grade"] = decision.get("score_text") or _text(student.get("ai_score"))
    if allow_comment_push and _feedback_present(student, ai_result):
        payload["comment"] = {"text_comment": _text(student.get("ai_feedback"))}
    return payload


def _policy_version(context: dict) -> int:
    policy = _mapping(context.get("push_policy"))
    try:
        return int(policy.get("policy_version", POLICY_VERSION))
    except (TypeError, ValueError):
        return POLICY_VERSION


def _receipt_id(*, context: dict, student: dict, idempotency_key: str, timestamp: str) -> str:
    basis = "|".join(
        [
            _text(context.get("course_id")),
            _text(context.get("assignment_id")),
            _student_user_id(student),
            idempotency_key,
            timestamp,
        ]
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def _write_receipt(receipt_dir: str | None, receipt: dict) -> str | None:
    if not receipt_dir:
        return None
    path = Path(receipt_dir)
    path.mkdir(parents=True, exist_ok=True)
    receipt_path = path / f"{receipt['receipt_id']}.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(receipt_path)


def _canvas_error(result) -> str:
    if isinstance(result, tuple) and len(result) >= 2 and result[1]:
        return _text(result[1])
    if isinstance(result, dict) and result.get("ok") is False:
        return _text(result.get("error") or "Canvas write failed")
    return ""


def _student_state(student: dict) -> dict:
    return _mapping(student.get("_autopush_state"))


def _preflight_receipt_dir(receipt_dir: str | None) -> str | None:
    """Preflight the receipt directory: create it, write a sentinel, and remove it.

    Returns the receipt_dir on success, None on failure.
    """
    if not receipt_dir:
        return None
    try:
        path = Path(receipt_dir)
        path.mkdir(parents=True, exist_ok=True)
        sentinel = path / ".preflight_sentinel"
        sentinel.write_text("ok")
        sentinel.unlink(missing_ok=True)
        return receipt_dir
    except OSError:
        return None


def run_autopush_for_session(
    *,
    context: dict,
    session: dict,
    assignment: dict,
    canvas_states_by_user: dict[str, dict] | None,
    canvas_send,
    receipt_dir: str | None = None,
    now=None,
) -> dict:
    context_map = _mapping(context)
    assignment_map = _mapping(assignment)
    session_map = _mapping(session)
    canvas_states = canvas_states_by_user or {}
    course_id = _text(context_map.get("course_id"))
    assignment_id = _text(context_map.get("assignment_id") or assignment_map.get("id"))
    summary = {
        "ok": True,
        "pushed": 0,
        "needs_review": 0,
        "blocked": 0,
        "evaluated": 0,
        "reason_counts": {},
        "errors": [],
        "student_results": [],
        "receipts": [],
    }

    # Preflight the receipt directory once before any PUT.
    # Missing workspace/receipt resolution must produce skipped_reason and zero PUTs.
    effective_receipt_dir = _preflight_receipt_dir(receipt_dir)
    if not effective_receipt_dir:
        summary["skipped_reason"] = "receipt_dir_unavailable"
        return summary

    for student in _student_rows(session_map):
        user_id = _student_user_id(student)
        if not user_id:
            continue
        # Pass explicit missing sentinel when user is absent from fresh state
        canvas_state = canvas_states.get(user_id) or canvas_states.get(_text(user_id))
        if canvas_state is None:
            canvas_state = {"canvas_state_present": False}

        existing_key = _text(student.get("autopush_idempotency_key"))
        if student.get("posted") is True and existing_key:
            result = {
                "user_id": user_id,
                "decision": "blocked",
                "reason": "already_pushed",
                "receipt_id": _text(student.get("autopush_receipt_id")),
                "idempotency_key": existing_key,
            }
            summary["evaluated"] += 1
            summary["blocked"] += 1
            summary["reason_counts"]["already_pushed"] = summary["reason_counts"].get("already_pushed", 0) + 1
            summary["student_results"].append(result)
            continue

        decision = evaluate_student_for_autopush(
            context=context_map,
            assignment=assignment_map,
            student=student,
            ai_result={
                "score": student.get("ai_score"),
                "feedback": student.get("ai_feedback"),
            },
            canvas_state=canvas_state,
        )
        decision_name = _text(decision.get("decision"))
        idempotency_key = _text(decision.get("idempotency_key"))
        summary["evaluated"] += 1
        if decision_name != "auto_push_allowed":
            reason = _text(decision.get("blocked_reason") or decision.get("review_needed_reason"))
            if decision_name == "needs_review":
                summary["needs_review"] += 1
            else:
                summary["blocked"] += 1
            summary["reason_counts"][reason] = summary["reason_counts"].get(reason, 0) + 1
            summary["student_results"].append(
                {
                    "user_id": user_id,
                    "decision": decision_name,
                    "reason": reason,
                    "receipt_id": "",
                    "idempotency_key": idempotency_key,
                }
            )
            continue

        payload = _build_canvas_payload(context_map, assignment_map, student, decision)
        payload = apply_lateness_to_submission_payload(payload, student)
        path = f"/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions/{user_id}"
        try:
            send_result = canvas_send("PUT", path, deepcopy(payload))
        except Exception as exc:  # pragma: no cover - error path exercised by tests
            summary["ok"] = False
            summary["blocked"] += 1
            summary["reason_counts"]["canvas_send_error"] = summary["reason_counts"].get("canvas_send_error", 0) + 1
            summary["errors"].append({"user_id": user_id, "reason": "canvas_send_error", "message": str(exc)})
            summary["student_results"].append(
                {
                    "user_id": user_id,
                    "decision": "blocked",
                    "reason": "canvas_send_error",
                    "receipt_id": "",
                    "idempotency_key": idempotency_key,
                }
            )
            continue
        send_error = _canvas_error(send_result)
        if send_error:
            summary["ok"] = False
            summary["blocked"] += 1
            summary["reason_counts"]["canvas_send_error"] = summary["reason_counts"].get("canvas_send_error", 0) + 1
            summary["errors"].append({"user_id": user_id, "reason": "canvas_send_error", "message": send_error})
            summary["student_results"].append(
                {
                    "user_id": user_id,
                    "decision": "blocked",
                    "reason": "canvas_send_error",
                    "receipt_id": "",
                    "idempotency_key": idempotency_key,
                }
            )
            continue

        timestamp = _now_iso(now)
        receipt = {
            "receipt_id": _receipt_id(context=context_map, student=student, idempotency_key=idempotency_key, timestamp=timestamp),
            "timestamp": timestamp,
            "course_id": course_id,
            "assignment_id": assignment_id,
            "user_id": user_id,
            "idempotency_key": idempotency_key,
            "pushed_fields": {
                "grade": "posted_grade" in payload.get("submission", {}),
                "comment": "comment" in payload and bool(_text(payload.get("comment", {}).get("text_comment"))),
            },
            "policy_version": _policy_version(context_map),
            "canvas_path": path,
        }
        try:
            receipt_path = _write_receipt(effective_receipt_dir, receipt)
            if receipt_path:
                receipt["receipt_path"] = receipt_path
        except Exception as exc:
            # Best-effort: the Canvas write succeeded, but receipt capture failed
            summary["ok"] = False
            summary["errors"].append({"user_id": user_id, "reason": "receipt_write_error", "message": str(exc)})
            receipt["receipt_error"] = "receipt_write_error"
        summary["receipts"].append(receipt)
        summary["pushed"] += 1
        summary["reason_counts"]["pushed"] = summary["reason_counts"].get("pushed", 0) + 1
        student["posted"] = True
        student["status"] = "auto_pushed"
        student["autopush_receipt_id"] = receipt["receipt_id"]
        student["autopush_idempotency_key"] = idempotency_key
        student["autopush_pushed_at"] = timestamp
        summary["student_results"].append(
            {
                "user_id": user_id,
                "decision": "auto_push_allowed",
                "reason": "",
                "receipt_id": receipt["receipt_id"],
                "idempotency_key": idempotency_key,
            }
        )

    return summary
