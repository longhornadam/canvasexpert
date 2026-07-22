"""Shared local-read/join helpers for Student Reports and merged portfolios.

Assembles one course's joined assignment+submission records from the typed
private-mirror read service (`api/mirror/read_service.py`) into the same nested
shape `api/student_packet.py::build_packet` already expects from a live Canvas
fetch, and resolves the comment-author display rule the private mirror already
applies everywhere else (comments have never stored author names — see
`api/mirror/store.py::_comment_record`).

Two consumers share the one underlying join pass (`_joined_course_records`):
`build_packet` (single-student, multi-course — filters to one student) and
`portfolio_service.py::build_merged_portfolios` (single-course, multi-student —
groups by every student).

Also provides `local_course_freshness`/`write_source_manifest`: a private,
non-rendered per-course source/freshness disclosure, written by both report
generators into a `_source_manifest.json` sidecar. This is a separate concern
from `student_packet.py`'s existing `_manifest.json` (a change-detection dedupe
cache keyed by content signature) — the two files/concerns never mix.
"""
from __future__ import annotations

import json
import os
import tempfile

from api.webui import workspace
from api.mirror import queries as mirror_queries
from api.mirror import read_service
from api.work_registry.providers.home_attention import _PROVEN_STAFF_ROLES, _author_role

# Single generic label for any of home_attention's proven staff roles (admin,
# administrator, instructor, staff, ta, teacher, teaching_assistant) — the report
# does not distinguish among them.
STAFF_LABEL = "Instructor"


def _joined_course_records(course_id, *, root=None) -> list[dict] | None:
    """Join one course's local assignments+comment-aware submissions for every student.

    Returns ``None`` (meaning: use the existing live fallback for this course)
    unless both the ``private_assignments`` and ``private_submission_comments``
    envelopes report ``state == "current"`` at the configured serve-age bound
    (``mirror_queries._serve_max_age_hours()``) — the local path is never used
    with incomplete, stale, or comment-aged data. ``private_submission_comments``
    reuses ``private_submissions``' own normalized rows internally (see
    `read_service.py`), so this reads exactly two top-level scopes, not three.
    Otherwise returns a list of every student's submission records in the exact
    nested shape downstream report code already expects (``s["assignment"]["name"]``,
    ``s["score"]``, ``s.get("assignment", {}).get(...)``).

    This is the one shared read+join pass behind both
    ``local_course_submissions`` (filtered to one student) and
    ``local_course_submissions_by_user`` (grouped by every student) — no
    duplicated read/join logic between the two public functions.
    """
    max_age_hours = mirror_queries._serve_max_age_hours()
    assignments = read_service.private_assignments(course_id, root=root, max_age_hours=max_age_hours)
    comments = read_service.private_submission_comments(course_id, root=root, max_age_hours=max_age_hours)
    if assignments["state"] != "current" or comments["state"] != "current":
        return None
    assignments_by_id = {a["id"]: a for a in assignments["records"]}
    joined = []
    for sub in comments["records"]:
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
    joined = _joined_course_records(course_id, root=root)
    if joined is None:
        return None
    wanted = str(user_id)
    return [record for record in joined if str(record.get("user_id") or "") == wanted]


def local_course_submissions_by_user(course_id, *, root=None) -> dict[str, list[dict]] | None:
    """Join one course's local assignments+submissions for every student, grouped.

    Returns ``None`` under the identical not-current gate as
    ``local_course_submissions``. Otherwise returns a dict keyed by ``user_id``
    (string) of every student's joined records for the course, in the identical
    per-record nested shape. Reads and joins the whole course exactly once —
    callers with several students to serve should call this once, not per
    student (see `portfolio_service.py::build_merged_portfolios`).
    """
    joined = _joined_course_records(course_id, root=root)
    if joined is None:
        return None
    grouped: dict[str, list[dict]] = {}
    for record in joined:
        key = str(record.get("user_id") or "")
        grouped.setdefault(key, []).append(record)
    return grouped


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


def local_course_freshness(course_id, *, root=None) -> dict:
    """Report one course's source/freshness for private disclosure only.

    Reads `private_assignments`/`private_submission_comments` independently
    (the same two envelopes `_joined_course_records` reads, at the same
    ``mirror_queries._serve_max_age_hours()`` bound, but not through it and not
    for their records — purely for freshness metadata). Returns
    ``{"source": "mirror", "synced_at": <min of both envelopes'
    last_success_at>}`` exactly when both envelopes report ``state ==
    "current"`` — i.e. exactly when `local_course_submissions`/
    `local_course_submissions_by_user` would return non-``None`` for this
    course. Missing, corrupt, or aged comment state can never be reported as
    mirror-current here. Otherwise returns ``{"source": "canvas", "synced_at": ""}``.

    Never calls Canvas; never duplicates or depends on
    `_joined_course_records`'s return value.
    """
    max_age_hours = mirror_queries._serve_max_age_hours()
    assignments = read_service.private_assignments(course_id, root=root, max_age_hours=max_age_hours)
    comments = read_service.private_submission_comments(course_id, root=root, max_age_hours=max_age_hours)
    if assignments["state"] != "current" or comments["state"] != "current":
        return {"source": "canvas", "synced_at": ""}
    synced_at = min(assignments["last_success_at"], comments["last_success_at"])
    return {"source": "mirror", "synced_at": synced_at}


def write_source_manifest(dest_dir, entries):
    """Atomically write/merge a private `_source_manifest.json` sidecar.

    Keyed by ``course_id``; each value is
    ``{"course_name", "source", "synced_at", "generated_at"}``. Merging updates
    only the course ids present in ``entries`` — any other course's prior
    entry is left untouched, matching `_manifest.json`'s existing
    merge-by-course-id convention. Tolerates a missing/corrupt existing file
    exactly like `student_packet.py::build_packet`'s existing `_manifest.json`
    try/except pattern.

    The write itself is atomic: the merged manifest is written to a fresh
    temporary file in ``dest_dir`` (never elsewhere — it holds private data),
    flushed and fsynced, then swapped onto the destination with ``os.replace``
    (atomic even over an existing file, including on Windows for closed
    handles). If anything fails before the swap, the prior destination file is
    left exactly as it was and the temporary file is removed best-effort;
    the exception still propagates.

    This is a distinct, private, never-rendered sidecar file — a separate
    concern from `_manifest.json`'s change-detection dedupe cache. Contains no
    signed URLs and no absolute filesystem paths.
    """
    path = os.path.join(dest_dir, "_source_manifest.json")
    try:
        with open(workspace.extended_path(path), encoding="utf-8") as f:
            manifest = json.load(f)
        if not isinstance(manifest, dict):
            manifest = {}
    except Exception:
        manifest = {}
    manifest.update(entries)

    # mkstemp(dir=extended) returns an already-\\?\-prefixed tmp_path, so the
    # os.replace/os.remove below inherit long-path safety; wrap `path` too.
    fd, tmp_path = tempfile.mkstemp(prefix="_source_manifest.", suffix=".tmp",
                                    dir=workspace.extended_path(dest_dir))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, workspace.extended_path(path))
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
