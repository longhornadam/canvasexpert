"""Shared local-read/join helpers for Student Reports.

Assembles one course's joined assignment+submission records from the typed
private-mirror read service (`api/mirror/read_service.py`) into the same nested
shape `api/student_packet.py::build_packet` already expects from a live Canvas
fetch, and resolves the comment-author display rule the private mirror already
applies everywhere else (comments have never stored author names — see
`api/mirror/store.py::_comment_record`).

This module has one consumer today (`build_packet`); the deferred
`portfolio_service.py::build_merged_portfolios` migration is expected to reuse
the same joining logic for a multi-student cohort.
"""
from __future__ import annotations

from api.mirror import read_service
from api.work_registry.providers.home_attention import _PROVEN_STAFF_ROLES, _author_role

# Single generic label for any of home_attention's proven staff roles (admin,
# administrator, instructor, staff, ta, teacher, teaching_assistant) — the report
# does not distinguish among them.
STAFF_LABEL = "Instructor"


def local_course_submissions(course_id, user_id, *, root=None) -> list[dict] | None:
    """Join one course's local assignments+submissions for one student.

    Returns ``None`` (meaning: use the existing live fallback for this course)
    unless both the ``private_assignments`` and ``private_submissions`` envelopes
    report ``state == "current"`` — the local path is never used with
    incomplete/stale data. Otherwise returns a list of submission records in the
    exact nested shape `build_packet`'s downstream code already expects
    (``s["assignment"]["name"]``, ``s["score"]``, ``s.get("assignment", {}).get(...)``).

    An empty list is a legitimate "current, but this student has no submissions
    in this course" result — distinct from ``None``, which means "not current."
    """
    assignments = read_service.private_assignments(course_id, root=root, max_age_hours=None)
    submissions = read_service.private_submissions(course_id, root=root, max_age_hours=None)
    if assignments["state"] != "current" or submissions["state"] != "current":
        return None
    assignments_by_id = {a["id"]: a for a in assignments["records"]}
    wanted = str(user_id)
    joined = []
    for sub in submissions["records"]:
        if str(sub.get("user_id") or "") != wanted:
            continue
        assignment = assignments_by_id.get(str(sub.get("assignment_id") or ""))
        if assignment is None:
            continue
        record = dict(sub)
        record["assignment"] = {
            "id": assignment.get("id"),
            "name": assignment.get("name"),
            "due_at": assignment.get("due_at"),
            "points_possible": assignment.get("points_possible"),
            "description": assignment.get("description"),
        }
        joined.append(record)
    return joined


def comment_author_label(author_id, author_role, report_user_id, report_student_name):
    """Resolve one comment's display label per the locked comment-display rule.

    - The report's own student's comments show ``report_student_name``.
    - A proven-staff author (the exact role vocabulary already defined in
      `home_attention._PROVEN_STAFF_ROLES`) shows a generic role label.
    - Any other author's name is not guessed at: this returns ``""`` so the
      comment still renders (via `student_packet._info_blocks`'s blank-label
      formatting) without a name, rather than being dropped — the comment's
      substantive content still matters to the report even when its author
      can't be attributed.
    """
    author_id = str(author_id or "")
    if author_id and report_user_id is not None and author_id == str(report_user_id):
        return report_student_name
    if str(author_role or "").casefold() in _PROVEN_STAFF_ROLES:
        return STAFF_LABEL
    return ""


def apply_comment_display(subs, report_user_id, report_student_name):
    """Mutate ``subs`` in place: relabel each submission's comments per the
    locked comment-display rule. Every comment is kept — an unattributable
    author's name is blanked (never guessed at, never dropped); the comment's
    text still matters to the report.

    Only ever called for the local-current path: local-mirror comments never
    stored a real author name to begin with (`store.py::_comment_record`), so
    this display rule is what recovers a usable label. Live-fallback ``subs``
    come straight from a live Canvas call and already carry real
    ``author_name`` values exactly as `_info_blocks` reads them today — do not
    call this for that path.
    """
    for sub in subs:
        comments = sub.get("submission_comments")
        if not isinstance(comments, list):
            continue
        relabeled = []
        for comment in comments:
            if not isinstance(comment, dict):
                continue
            label = comment_author_label(
                comment.get("author_id"), _author_role(comment),
                report_user_id, report_student_name,
            )
            comment = dict(comment)
            comment["author_name"] = label
            relabeled.append(comment)
        sub["submission_comments"] = relabeled
    return subs
