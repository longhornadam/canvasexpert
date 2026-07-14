"""PowerGrader session actions — save grades and guarded Canvas pushes."""

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone

from powergrader import late_catchup


REVIEW_TTL = timedelta(minutes=15)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _digest(value) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def invalidate_pending_review(session: dict) -> None:
    session.pop("pending_push_review", None)
    session.pop("pending_new_quiz_review", None)


def _new_quiz_decisions(raw: str) -> tuple[list[dict] | None, str | None]:
    try:
        values = json.loads(raw)
    except Exception:
        return None, "invalid_item_decisions"
    if not isinstance(values, list):
        return None, "invalid_item_decisions"
    clean = []
    for value in values:
        if not isinstance(value, dict) or not value.get("item_id"):
            return None, "invalid_item_decisions"
        try:
            score = float(value.get("score"))
        except (TypeError, ValueError):
            return None, "invalid_item_decisions"
        clean.append({
            "item_id": str(value["item_id"]), "score": score,
            "teacher_feedback": str(value.get("teacher_feedback") or ""),
            "ta_feedback": str(value.get("ta_feedback") or ""),
        })
    return clean, None


def review_new_quiz_finalization(session_id: str, *, user_id: str, decisions_json: str,
                                 load_session, save_session, preflight) -> tuple[dict, int]:
    session = load_session(session_id)
    if not session:
        return {"ok": False, "code": "session_not_found", "error": "Session not found."}, 404
    if not session.get("new_quiz_item_finalization_supported"):
        return {"ok": False, "code": "new_quiz_finalization_unavailable", "error": "This session does not support New Quiz item finalization."}, 200
    student = next((item for item in session.get("students", []) if str(item.get("user_id")) == str(user_id)), None)
    if not student:
        return {"ok": False, "code": "student_not_found", "error": "Student not found in session."}, 200
    if student.get("speedgrader_required"):
        return {"ok": False, "code": "speedgrader_required", "error": "This student's New Quiz evidence requires SpeedGrader review."}, 200
    decisions, error = _new_quiz_decisions(decisions_json)
    if error:
        return {"ok": False, "code": error, "error": "Enter one valid teacher score for every reviewed item."}, 200
    try:
        baseline = preflight(session, student, decisions)
    except Exception as exc:
        code = getattr(exc, "code", "new_quiz_preflight_failed")
        return {"ok": False, "code": code, "error": "Canvas could not freeze this student's current New Quiz result."}, 200
    pending = {
        "token": secrets.token_urlsafe(32), "created_at": _iso(_now()),
        "expires_at": _iso(_now() + REVIEW_TTL), "user_id": str(user_id),
        "result_id": baseline["result_id"], "state_digest": baseline["state_digest"],
        "decision_digest": baseline["decision_digest"],
    }
    session["pending_new_quiz_review"] = pending
    save_session(session)
    return {"ok": True, "review_token": pending["token"], "expires_at": pending["expires_at"], "item_count": len(decisions)}, 200


def finalize_new_quiz(session_id: str, *, user_id: str, review_token: str, decisions_json: str,
                      load_session, save_session, apply) -> tuple[dict, int]:
    session = load_session(session_id)
    if not session:
        return {"ok": False, "code": "session_not_found", "error": "Session not found."}, 404
    pending = session.get("pending_new_quiz_review") or {}
    decisions, error = _new_quiz_decisions(decisions_json)
    decision_digest = _digest(decisions) if decisions else ""
    if not error and session.setdefault("new_quiz_finalized_digests", {}).get(str(user_id)) == decision_digest:
        return {"ok": True, "status": "already_applied", "code": "already_applied"}, 200
    if error or not pending or pending.get("user_id") != str(user_id) or pending.get("token") != review_token:
        return _review_error("review_mismatch")
    try:
        if _now() >= datetime.fromisoformat(pending["expires_at"]):
            invalidate_pending_review(session); save_session(session)
            return _review_error("review_expired")
    except (KeyError, ValueError, TypeError):
        return _review_error("review_required")
    if _digest(decisions) != pending.get("decision_digest"):
        return _review_error("payload_changed")
    key = _digest({"user_id": str(user_id), "decision_digest": pending["decision_digest"], "state_digest": pending["state_digest"]})
    if session.setdefault("new_quiz_idempotency", {}).get(str(user_id)) == key:
        return {"ok": True, "status": "already_applied", "code": "already_applied"}, 200
    student = next((item for item in session.get("students", []) if str(item.get("user_id")) == str(user_id)), None)
    if not student or student.get("speedgrader_required"):
        return {"ok": False, "code": "speedgrader_required", "error": "This student's New Quiz evidence requires SpeedGrader review."}, 200
    try:
        result = apply(session, student, decisions, pending)
    except Exception as exc:
        code = getattr(exc, "code", "write_unknown")
        session.setdefault("new_quiz_receipts", []).append({"ts": _iso(_now()), "user_id": str(user_id), "outcome": code, "content_minimized": True})
        # An ambiguous or rejected write must never be retried through the
        # same frozen approval.  The teacher reviews Canvas first, then starts
        # a new explicit review if another attempt is warranted.
        invalidate_pending_review(session)
        save_session(session)
        return {"ok": False, "code": code, "error": "New Quiz finalization was not verified; review in SpeedGrader before retrying."}, 409
    session["new_quiz_idempotency"][str(user_id)] = key
    session["new_quiz_finalized_digests"][str(user_id)] = decision_digest
    student["new_quiz_finalized"] = True
    session.setdefault("new_quiz_receipts", []).append({"ts": _iso(_now()), "user_id": str(user_id), "outcome": "verified", "result_digest": result.get("state_digest"), "content_minimized": True})
    invalidate_pending_review(session)
    save_session(session)
    return {"ok": True, "status": "finalized", "code": "finalized"}, 200


def _parse_ids(raw: str, *, allow_empty: bool = True) -> tuple[list[str] | None, str | None]:
    if not raw.strip():
        return ([] if allow_empty else None), None if allow_empty else "invalid_selection"
    try:
        values = json.loads(raw)
    except Exception:
        return None, "invalid_selection"
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        return None, "invalid_selection"
    ids = [value for value in values if value.strip()]
    if len(ids) != len(set(ids)):
        return None, "invalid_selection"
    return ids, None


def _writeback_mode(session: dict) -> str:
    """What this session may write to Canvas.

    "full" — grades and comments through the Submissions API.
    "comments_only" — assignment-level comments only (New Quiz sessions:
    scores belong to the quiz engine, which has no reviewed write transport
    yet, but submission comments are ordinary Canvas data — verified live
    2026-07-14).
    "none" — legacy New Quiz sessions created before the comment lane.
    """
    if session.get("canvas_writeback_supported", True):
        return "full"
    if session.get("comment_writeback_supported") is True:
        return "comments_only"
    return "none"


def _payload(student: dict, *, comments_only: bool = False) -> dict:
    score = student.get("teacher_score")
    feedback = (student.get("teacher_feedback") or "").strip()
    payload: dict = {}
    if comments_only:
        # Never touch the score or lateness of a quiz-engine-owned grade.
        if feedback:
            payload["comment"] = {"text_comment": feedback}
        return payload
    if score is not None:
        payload["submission"] = {"posted_grade": str(score)}
    if feedback:
        payload["comment"] = {"text_comment": feedback}
    late_catchup.apply_lateness_to_submission_payload(payload, student)
    return payload


def _snapshot(data: dict) -> dict:
    submission = data.get("submission") if isinstance(data.get("submission"), dict) else data
    comments_key = "submission_comments" if "submission_comments" in data else "comments" if "comments" in data else None
    comments = data.get(comments_key) if comments_key else None
    comments = comments if isinstance(comments, list) else []
    latest = {}
    if comments:
        latest = sorted(comments, key=lambda item: str(item.get("created_at") or ""))[-1] or {}
    return {
        "score": submission.get("score"),
        "grade": submission.get("grade"),
        "graded_at": submission.get("graded_at"),
        "updated_at": submission.get("updated_at"),
        "comments_available": comments_key is not None,
        "comment_count": len(comments),
        "latest_comment": {
            "id": latest.get("id"),
            "created_at": latest.get("created_at"),
        },
    }


def _same_score_baseline(before: dict, after: dict) -> bool:
    return all(before.get(key) == after.get(key) for key in ("score", "grade", "graded_at", "updated_at"))


def _same_comments(before: dict, after: dict) -> bool:
    return (
        before.get("comments_available")
        and after.get("comments_available")
        and before.get("comment_count") == after.get("comment_count")
        and before.get("latest_comment") == after.get("latest_comment")
    )


def _path(session: dict, user_id: str) -> str:
    return (
        f"/api/v1/courses/{session['course_id']}/assignments/{session['assignment_id']}"
        f"/submissions/{user_id}"
    )


def _fetch_snapshot(session: dict, user_id: str, canvas_get) -> tuple[dict | None, str | None]:
    data, error = canvas_get(
        _path(session, user_id),
        params={"include[]": "submission_comments"},
        timeout=5,
    )
    if error or not isinstance(data, dict):
        return None, "review_fetch_failed"
    return _snapshot(data), None


def _eligible_students(session: dict, *, comments_only: bool = False) -> dict[str, dict]:
    return {
        str(student.get("user_id")): student
        for student in session.get("students", [])
        if student.get("user_id") is not None
        and student.get("status") == "approved"
        and not student.get("posted")
        and _payload(student, comments_only=comments_only)
    }


def review_push(
    session_id: str,
    *,
    user_ids: str,
    load_session,
    save_session,
    canvas_get,
) -> tuple[dict, int]:
    session = load_session(session_id)
    if not session:
        return {"ok": False, "code": "session_not_found", "error": "Session not found."}, 404
    mode = _writeback_mode(session)
    if mode == "none":
        return {"ok": False, "code": "canvas_writeback_unsupported", "error": "This session was created before New Quiz comment posting. Start a new session to post feedback comments."}, 200
    comments_only = mode == "comments_only"
    requested, error = _parse_ids(user_ids)
    if error:
        return {"ok": False, "code": error, "error": "Select valid submissions for review."}, 200
    eligible = _eligible_students(session, comments_only=comments_only)
    ordered_ids = requested or [str(student.get("user_id")) for student in session.get("students", []) if str(student.get("user_id")) in eligible]
    if not ordered_ids or any(user_id not in eligible for user_id in ordered_ids):
        error_text = ("Selected submissions have no approved feedback to post. New Quiz sessions post feedback comments only; scores are entered in Canvas."
                      if comments_only else "Selected submissions are no longer eligible.")
        return {"ok": False, "code": "invalid_selection", "error": error_text}, 200

    baselines = {}
    payload_digests = {}
    target_digests = {}
    targets = []
    for user_id in ordered_ids:
        student = eligible[user_id]
        baseline, fetch_error = _fetch_snapshot(session, user_id, canvas_get)
        if fetch_error:
            return {"ok": False, "code": fetch_error, "error": "Could not capture the Canvas review baseline."}, 200
        payload = _payload(student, comments_only=comments_only)
        baselines[user_id] = baseline
        payload_digests[user_id] = _digest(payload)
        target_digests[user_id] = _digest({"user_id": user_id, "payload": payload, "baseline": baseline})
        targets.append({
            "user_id": user_id,
            "has_score": "submission" in payload,
            "has_feedback": "comment" in payload,
            "current_score": baseline.get("score"),
            "current_grade": baseline.get("grade"),
            "comment_count": baseline.get("comment_count"),
            "comments_available": baseline.get("comments_available"),
        })

    pending = {
        "token": secrets.token_urlsafe(32),
        "created_at": _iso(_now()),
        "expires_at": _iso(_now() + REVIEW_TTL),
        "user_ids": ordered_ids,
        "payload_digests": payload_digests,
        "target_digests": target_digests,
        "baselines": baselines,
        "overall_digest": _digest({"user_ids": ordered_ids, "payload_digests": payload_digests, "baselines": baselines}),
    }
    session["pending_push_review"] = pending
    save_session(session)
    return {
        "ok": True,
        "review_token": pending["token"],
        "expires_at": pending["expires_at"],
        "user_ids": ordered_ids,
        "overall_digest": pending["overall_digest"],
        "targets": targets,
        "writeback_mode": mode,
    }, 200


def save_grade(
    session_id: str,
    *,
    user_id: str,
    teacher_score: str,
    teacher_feedback: str,
    status: str,
    load_session,
    save_session,
) -> tuple[dict, int]:
    """Save one student's grade into a session and invalidate any review."""
    session = load_session(session_id)
    if not session:
        return {"ok": False, "error": "Session not found."}, 404

    score_val = None
    if teacher_score.strip():
        try:
            score_val = float(teacher_score.strip())
        except ValueError:
            return {"ok": False, "error": "Invalid score value."}, 200

    for student in session["students"]:
        if student["user_id"] == user_id:
            student["teacher_score"] = score_val
            student["teacher_feedback"] = teacher_feedback.strip()
            student["status"] = status if status in ("approved", "skipped", "pending") else "approved"
            invalidate_pending_review(session)
            save_session(session)
            approved = sum(1 for item in session["students"] if item.get("status") == "approved")
            return {"ok": True, "approved": approved}, 200

    return {"ok": False, "error": "Student not found in session."}, 200


def _review_error(code: str) -> tuple[dict, int]:
    messages = {
        "review_required": "Review required before push.",
        "review_expired": "The review expired. Review again before pushing.",
        "review_mismatch": "The selected submissions do not match the review.",
        "payload_changed": "The reviewed grade or feedback changed. Review again.",
        "drift_detected": "Canvas changed after review. Review again before pushing.",
        "comments_unavailable": "Canvas comments could not be verified for feedback.",
        "review_fetch_failed": "Canvas could not be checked before pushing.",
    }
    return {"ok": False, "code": code, "error": messages.get(code, "Push review is no longer valid.")}, 409


def push_grades(
    session_id: str,
    *,
    user_ids: str,
    review_token: str,
    load_session,
    save_session,
    canvas_send,
    canvas_get,
) -> tuple[dict, int]:
    """Apply only a still-valid, drift-checked frozen review."""
    session = load_session(session_id)
    if not session:
        return {"ok": False, "code": "session_not_found", "error": "Session not found."}, 404
    mode = _writeback_mode(session)
    if mode == "none":
        return {"ok": False, "code": "canvas_writeback_unsupported", "error": "This session was created before New Quiz comment posting. Start a new session to post feedback comments."}, 200
    comments_only = mode == "comments_only"
    pending = session.get("pending_push_review")
    if not pending or not review_token:
        return _review_error("review_required")
    try:
        if _now() >= datetime.fromisoformat(pending["expires_at"]):
            invalidate_pending_review(session)
            save_session(session)
            return _review_error("review_expired")
    except (KeyError, ValueError, TypeError):
        return _review_error("review_required")
    requested, error = _parse_ids(user_ids, allow_empty=False)
    if error or review_token != pending.get("token") or requested != pending.get("user_ids"):
        return _review_error("review_mismatch")

    students = {str(student.get("user_id")): student for student in session.get("students", [])}
    idempotency = session.setdefault("push_idempotency", {})
    preflight = []
    for user_id in requested:
        student = students.get(user_id)
        if not student or not _payload(student, comments_only=comments_only):
            return _review_error("payload_changed")
        payload = _payload(student, comments_only=comments_only)
        payload_digest = _digest(payload)
        if payload_digest != pending.get("payload_digests", {}).get(user_id):
            return _review_error("payload_changed")
        target_digest = pending.get("target_digests", {}).get(user_id)
        if idempotency.get(user_id) == target_digest:
            preflight.append((user_id, student, payload, target_digest, "already_applied"))
            continue
        if student.get("status") != "approved" or student.get("posted"):
            return _review_error("payload_changed")
        current, fetch_error = _fetch_snapshot(session, user_id, canvas_get)
        if fetch_error:
            return _review_error(fetch_error)
        baseline = pending.get("baselines", {}).get(user_id) or {}
        if "comment" in payload:
            if not _same_comments(baseline, current):
                return _review_error("comments_unavailable" if not current.get("comments_available") else "drift_detected")
        if "submission" in payload and not _same_score_baseline(baseline, current):
            return _review_error("drift_detected")
        preflight.append((user_id, student, payload, target_digest, "pending"))

    results = []
    pushed = 0
    for user_id, student, payload, target_digest, state in preflight:
        if state == "already_applied":
            student["posted"] = True
            student["status"] = "posted"
            results.append({"user_id": user_id, "status": "already_applied", "code": "already_applied"})
            continue
        _, send_error = canvas_send("PUT", _path(session, user_id), payload)
        if send_error:
            results.append({"user_id": user_id, "status": "failed", "code": "canvas_rejected"})
            continue
        student["posted"] = True
        student["status"] = "posted"
        idempotency[user_id] = target_digest
        pushed += 1
        results.append({"user_id": user_id, "status": "pushed", "code": "pushed"})

    if results:
        session.setdefault("push_log", []).append({
            "ts": _iso(_now()),
            "user_ids": requested,
            "results": results,
        })
        save_session(session)
    failed = sum(1 for result in results if result["status"] == "failed")
    return {
        "ok": failed == 0,
        "pushed": pushed,
        "results": results,
        "errors": [result["code"] for result in results if result["status"] == "failed"],
    }, 200
