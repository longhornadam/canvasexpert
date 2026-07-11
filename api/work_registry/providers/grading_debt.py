"""Cross-course grading-debt discovery with aggregate-only output."""

from __future__ import annotations

from collections import defaultdict

from . import (
    CourseTimeout,
    DiscoveryDeadline,
    ProviderFailure,
    call_canvas_get_all,
    check_deadline,
    finding,
    text,
)
from .powergrader import powergrader_evidence


def _number(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _comment_is_teacher(comment: dict, user_id: str) -> bool:
    if not isinstance(comment, dict):
        return False
    author = comment.get("author") if isinstance(comment.get("author"), dict) else {}
    author_id = text(comment.get("author_id") or author.get("id"))
    role = text(comment.get("author_role") or author.get("role") or author.get("type")).casefold()
    if author_id and author_id == user_id:
        return False
    if role in {"student", "student_view", "studentview"}:
        return False
    return bool(author_id or role or comment.get("author_name"))


def _teacher_touched(submission: dict, user_id: str) -> bool:
    if submission.get("score") is not None:
        return True
    comments = submission.get("submission_comments")
    return any(_comment_is_teacher(comment, user_id) for comment in (comments or []))


def _normalize_assignment_map(assignments: list[dict]) -> dict[str, dict]:
    return {
        text(item.get("id")): item
        for item in assignments
        if isinstance(item, dict) and text(item.get("id"))
    }


def scan_course(course_id: str, *, now, deadline, canvas_get_all) -> list[dict]:
    """Find submitted/pending-review work lacking teacher evidence."""
    check_deadline(deadline)
    assignments = call_canvas_get_all(
        canvas_get_all,
        f"/api/v1/courses/{course_id}/assignments",
        {"per_page": 100},
        deadline,
    )
    check_deadline(deadline)
    submissions = call_canvas_get_all(
        canvas_get_all,
        f"/api/v1/courses/{course_id}/students/submissions",
        {
            "student_ids[]": "all",
            "include[]": "submission_comments",
            "per_page": 100,
        },
        deadline,
    )
    assignment_map = _normalize_assignment_map(assignments)
    evidence = powergrader_evidence()
    aggregates: dict[str, dict] = defaultdict(lambda: {
        "total": 0,
        "pending": 0,
        "affected": 0,
        "latest_submitted_at": "",
        "latest_attempt_number": 0,
        "due_at": "",
    })
    for submission in submissions:
        if not isinstance(submission, dict):
            continue
        workflow = text(submission.get("workflow_state")).casefold()
        submitted_at = text(submission.get("submitted_at"))
        if workflow not in {"submitted", "pending_review"} or not submitted_at:
            continue
        assignment_id = text(submission.get("assignment_id"))
        assignment = assignment_map.get(assignment_id)
        if not assignment_id or assignment is None:
            continue
        row = aggregates[assignment_id]
        row["total"] += 1
        attempt = max(
            _number(submission.get("attempt"), _number(submission.get("submission_attempt"))),
            0,
        )
        if submitted_at > row["latest_submitted_at"]:
            row["latest_submitted_at"] = submitted_at
        row["latest_attempt_number"] = max(row["latest_attempt_number"], attempt)
        row["due_at"] = text(assignment.get("due_at"))
        user_id = text(submission.get("user_id"))
        touched = _teacher_touched(submission, user_id)
        session_key = (str(course_id), assignment_id, user_id)
        session_evidence = evidence.get(session_key)
        if session_evidence and not _later_than_evidence(submission, session_evidence):
            touched = True
        if not touched:
            row["pending"] += 1
            row["affected"] += 1
    output = []
    for assignment_id in sorted(aggregates):
        row = aggregates[assignment_id]
        if not row["pending"]:
            continue
        output.append(finding(
            kind="grade.debt",
            course_id=str(course_id),
            assignment_id=assignment_id,
            counts={key: row[key] for key in ("total", "pending", "affected")},
            now=now,
            latest_submitted_at=row["latest_submitted_at"],
            latest_attempt_number=row["latest_attempt_number"],
            due_at=row["due_at"],
            resumable_url="/powergrader",
        ))
    return output


def _later_than_evidence(submission: dict, evidence: dict) -> bool:
    submitted_at = text(submission.get("submitted_at"))
    evidence_at = text(evidence.get("at"))
    if not submitted_at or not evidence_at:
        return False
    try:
        from .powergrader import as_datetime
        current = as_datetime(submitted_at)
        prior = as_datetime(evidence_at)
        return current is not None and prior is not None and current > prior
    except Exception:
        return False


__all__ = ["scan_course"]
