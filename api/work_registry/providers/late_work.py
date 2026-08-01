"""Aggregate late-work discovery using the existing school-day calculations."""

from __future__ import annotations

from collections import defaultdict

from api.webui import config, deps, school_calendar
from api.webui.schooldays import _parse_iso_local, _school_days_late_detail

from . import CalendarNeedsAttention, WorkCourseReads, check_deadline, finding, text


def _int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def scan_course(course_id: str, *, now, reads: WorkCourseReads) -> list[dict]:
    check_deadline(reads._deadline)
    assignments = reads.assignments()
    check_deadline(reads._deadline)
    submissions = reads.submissions()
    extra_days = {
        text(item.get("id")): max(_int(item.get("days")), 0)
        for item in config.get_extra_time(course_id)
        if isinstance(item, dict) and text(item.get("id"))
    }
    assignments_by_id = {
        text(item.get("id")): item
        for item in assignments
        if isinstance(item, dict) and text(item.get("id")) and item.get("published", True)
    }

    candidates = []
    span_start = span_end = None
    for submission in submissions:
        if not isinstance(submission, dict) or submission.get("excused"):
            continue
        assignment_id = text(submission.get("assignment_id"))
        assignment = assignments_by_id.get(assignment_id)
        submitted_at = text(submission.get("submitted_at"))
        due_at = text(assignment.get("due_at")) if assignment else ""
        if not assignment or not submitted_at or not due_at:
            continue
        workflow = text(submission.get("workflow_state")).casefold()
        if workflow != "late" and submission.get("late") is not True:
            continue
        due = _parse_iso_local(due_at)
        submitted = _parse_iso_local(submitted_at)
        if not due or not submitted:
            continue
        candidates.append((submission, assignment_id, due, submitted, due_at, submitted_at))
        span_start = due.date() if span_start is None else min(span_start, due.date())
        span_end = submitted.date() if span_end is None else max(span_end, submitted.date())

    # No calendar (or one that can't cover every due/submitted date here)
    # means no reliable school-day math -- raise rather than silently treat
    # every day (weekends included) as instructional. The caller marks this
    # course's scan stale and falls back to its last-known-good findings
    # instead of confidently reporting zero.
    no_count: set[str] = set()
    if candidates:
        bell_schedules, _problems = deps.load_bell_schedules()
        result = school_calendar.resolve_instructional_range(
            span_start.isoformat(), span_end.isoformat(), set(bell_schedules))
        if result["state"] != "ready":
            raise CalendarNeedsAttention()
        no_count = set(result["no_count_dates"])

    aggregates: dict[str, dict] = defaultdict(lambda: {
        "total": 0,
        "pending": 0,
        "affected": 0,
        "latest_submitted_at": "",
        "latest_attempt_number": 0,
        "due_at": "",
    })
    for submission, assignment_id, due, submitted, due_at, submitted_at in candidates:
        school_days, _ = _school_days_late_detail(due, submitted, no_count)
        allowed_days = extra_days.get(text(submission.get("user_id")), 0)
        if school_days <= allowed_days:
            continue
        row = aggregates[assignment_id]
        row["total"] += 1
        row["pending"] += 1
        row["affected"] += 1
        row["latest_submitted_at"] = max(row["latest_submitted_at"], submitted_at)
        row["latest_attempt_number"] = max(
            row["latest_attempt_number"],
            max(_int(submission.get("attempt"), _int(submission.get("submission_attempt"))), 0),
        )
        row["due_at"] = due_at
    output = []
    for assignment_id in sorted(aggregates):
        row = aggregates[assignment_id]
        output.append(finding(
            kind="late.work",
            course_id=str(course_id),
            assignment_id=assignment_id,
            counts={key: row[key] for key in ("total", "pending", "affected")},
            now=now,
            latest_submitted_at=row["latest_submitted_at"],
            latest_attempt_number=row["latest_attempt_number"],
            due_at=row["due_at"],
            title=f"Late work · {row['affected']}",
            resumable_url=f"/gradebook?course_id={course_id}",
        ))
    return output


__all__ = ["scan_course"]
