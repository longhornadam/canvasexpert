"""Aggregate-only projections from local PowerGrader authorities."""

from __future__ import annotations

from api.work_registry import adapters

from . import as_datetime, safe_id, text


_TERMINAL = {"approved", "skipped", "posted", "auto_pushed"}


def project_local(*, course_id: str | None = None, now=None) -> list[dict]:
    """Project existing local summaries without opening private student rows."""
    jobs = adapters.collect_local_jobs()
    if not course_id:
        return jobs
    return [
        job for job in jobs
        if str(course_id) in {str(value) for value in (job.get("course_ids") or [])}
    ]


def _student_evidence(student: dict) -> tuple[bool, str]:
    status = text(student.get("status")).casefold()
    teacher_score = student.get("teacher_score")
    teacher_comment = (
        student.get("teacher_feedback")
        or student.get("teacher_comment")
        or student.get("feedback")
    )
    touched = teacher_score is not None or bool(str(teacher_comment or "").strip())
    terminal = status in _TERMINAL or student.get("posted") is True
    if not (touched or terminal):
        return False, ""
    graded_at = (
        student.get("graded_at")
        or student.get("teacher_graded_at")
        or student.get("updated_at")
        or ""
    )
    baseline = (
        student.get("baseline_submitted_at")
        or student.get("baseline_updated_at")
        or ""
    )
    return True, text(graded_at or baseline)


def _later_submission(student: dict, submitted_at: str) -> bool:
    current = as_datetime(submitted_at)
    if current is None:
        return False
    for key in (
        "graded_at", "teacher_graded_at", "baseline_submitted_at",
        "baseline_updated_at", "submission_baseline_at",
    ):
        baseline = as_datetime(student.get(key))
        if baseline is not None and current > baseline:
            return True
    baseline_obj = student.get("baseline")
    if isinstance(baseline_obj, dict):
        for key in ("submitted_at", "updated_at", "graded_at"):
            baseline = as_datetime(baseline_obj.get(key))
            if baseline is not None and current > baseline:
                return True
    return False


def powergrader_evidence() -> dict[tuple[str, str, str], dict]:
    """Return transient evidence keyed by course/assignment/user.

    The returned mapping is consumed immediately by the grading-debt provider and
    is never part of a cache, registry job, response, or log record.
    """
    evidence: dict[tuple[str, str, str], dict] = {}
    try:
        from api.powergrader import session_store
        summaries = session_store.list_session_summaries()
    except Exception:
        return evidence
    for summary in summaries if isinstance(summaries, list) else []:
        if not isinstance(summary, dict):
            continue
        session_id = safe_id(summary.get("session_id"))
        if not session_id:
            continue
        try:
            session = session_store.load_session(session_id)
        except Exception:
            continue
        if not isinstance(session, dict):
            continue
        course = text(session.get("course_id") or summary.get("course_id"))
        assignment = text(session.get("assignment_id") or summary.get("assignment_id"))
        if not course or not assignment:
            continue
        students = session.get("students")
        if not isinstance(students, list):
            continue
        for student in students:
            if not isinstance(student, dict):
                continue
            user_id = text(student.get("user_id"))
            if not user_id:
                continue
            touched, evidence_at = _student_evidence(student)
            if not touched:
                continue
            evidence[(course, assignment, user_id)] = {"at": evidence_at}
    return evidence


__all__ = ["powergrader_evidence", "project_local"]
