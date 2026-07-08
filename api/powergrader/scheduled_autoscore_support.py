"""Pure helpers for scheduled PowerGrader autoscore routines."""

from __future__ import annotations

import os
from datetime import datetime, timezone


def autoscore_job_label(job: dict) -> str:
    course = str(job.get("course_name") or job.get("course_id") or "").strip()
    assignment = str(job.get("assignment_name") or job.get("assignment_id") or "").strip()
    return " / ".join(part for part in (course, assignment) if part)


def autoscore_fetch_status(error: str) -> tuple[str | None, str]:
    text = (error or "").lower()
    if any(token in text for token in ("404", "not found", "403", "forbidden", "unauthorized")):
        return "failed", "Canvas assignment is no longer available."
    return None, "Could not refresh the Canvas assignment right now."


def autoscore_receipt_dir(job: dict, session_store) -> str | None:
    root = session_store.pg_dir()
    if not root:
        return None
    job_id = str(job.get("job_id") or job.get("assignment_id") or "scheduled-job")
    return os.path.join(root, "_private", "autopush_receipts", job_id)


def autoscore_canvas_states(submissions: list[dict] | None) -> dict[str, dict]:
    states: dict[str, dict] = {}
    for sub in submissions or []:
        uid = str(sub.get("user_id") or "").strip()
        if not uid:
            continue
        state: dict = {}
        if sub.get("score") is not None:
            state["existing_score"] = sub.get("score")
        comments = []
        for key in ("submission_comments", "comments"):
            raw = sub.get(key)
            if not isinstance(raw, list):
                continue
            for item in raw:
                if isinstance(item, dict):
                    text = item.get("comment") or item.get("text_comment") or item.get("body") or item.get("message")
                else:
                    text = item
                text = str(text or "").strip()
                if text:
                    comments.append(text)
        if comments:
            state["existing_comments"] = comments
        states[uid] = state
    return states


def autoscore_session_is_fully_pushed(session: dict) -> bool:
    students = session.get("students") or []
    if not students:
        return False
    for student in students:
        if student.get("posted") is not True:
            return False
        if not str(student.get("autopush_idempotency_key") or "").strip():
            return False
    return True


def autoscore_status_from_summary(result: dict, current_status: str) -> str:
    pushed = int(result.get("pushed") or 0)
    needs_review = int(result.get("needs_review") or 0)
    blocked = int(result.get("blocked") or 0)
    errors = list(result.get("errors") or [])
    student_results = list(result.get("student_results") or [])
    if pushed and not needs_review and not blocked and not errors:
        return "auto_pushed"
    if not pushed and student_results and all(r.get("reason") == "already_pushed" for r in student_results):
        return "auto_pushed"
    if pushed and (needs_review or blocked or errors):
        return "partial_auto_pushed"
    if not pushed and needs_review:
        return "needs_review"
    if not pushed and errors:
        return "failed"
    return current_status or "session_ready"


def autoscore_summary_payload(result: dict) -> dict:
    return {
        "pushed": int(result.get("pushed") or 0),
        "needs_review": int(result.get("needs_review") or 0),
        "blocked": int(result.get("blocked") or 0),
        "errors": [
            {"user_id": err.get("user_id"), "reason": err.get("reason")}
            for err in (result.get("errors") or [])
            if isinstance(err, dict)
        ],
    }


def autoscore_decisions_payload(result: dict) -> list[dict]:
    out = []
    for row in result.get("student_results") or []:
        if not isinstance(row, dict):
            continue
        out.append({
            "user_id": row.get("user_id"),
            "decision": row.get("decision"),
            "reason": row.get("reason"),
            "receipt_id": row.get("receipt_id"),
            "idempotency_key": row.get("idempotency_key"),
        })
    return out


def parse_routine_dt(value: str | None):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed