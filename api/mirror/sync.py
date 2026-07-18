"""CanvasMirror sync engine — the deterministic passes that keep the mirror fresh.

The passes take an injected legacy ``canvas_get_all`` (catalog pattern —
this module never imports the Canvas client) and an optional ``now=`` clock
for deterministic tests. ``full_pass`` and ``delta_pass`` additionally take
the complete-only assignment receipt before replacing membership:

  full_pass    backfill == nightly reconcile: fetch everything, rewrite
               collections with attempt-preserving replace merges, prune
               assignments/students that no longer exist, reset watermarks.
               Also the only pass that can fix ``missing``-flag drift —
               Canvas flips ``missing`` when a due date passes with no
               student action, which no delta can ever observe.
  delta_pass   two course-level questions since the last watermark:
               "anything submitted?" (with submission_history) and
               "anything graded?". Near-empty for stagnant courses.
  roster_pass  students + sections (cheap; rosters rarely change).

Watermarks advance only on success, to (pass start - 10 min overlap); the
store's merges are idempotent so overlap duplicates are harmless. Failures
degrade the pass envelope (stale/unavailable) and never touch collections.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from api.assignment_collection import acquire_assignment_collection

# Reuse the catalog's transport-error -> stable-code mapping so diagnostics
# read the same across both mirrors of Canvas data.
from api.course_catalog import _error_code

from . import new_quizzes, store


WATERMARK_OVERLAP_MINUTES = 10

# An assignment collection may alter private mirror membership only after the
# complete-client receipt and the existing normalizer both accept it. An empty
# or drastically shrunken authoritative collection still commits, but
# submission-file pruning for that shrink defers to the pass after this one.
# The next pass compares against the now-smaller committed index, so a genuine
# shrink prunes cleanly one pass later.
LARGE_SHRINK_RATIO = 0.5


def _overlapped(iso_z: str) -> str:
    moment = datetime.strptime(iso_z, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return (moment - timedelta(minutes=WATERMARK_OVERLAP_MINUTES)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _fetch_assignments(course_id, canvas_get_all_complete):
    return acquire_assignment_collection(course_id, canvas_get_all_complete)


def _assignment_receipt_error(rows, error, complete) -> str:
    """Validate the receipt before it can replace assignment membership."""
    if error:
        if error in {"pagination_incomplete", "invalid_response"}:
            return error
        return _error_code(error)
    if not complete:
        return "pagination_incomplete"
    if not isinstance(rows, list):
        return "invalid_response"
    assignment_ids = set()
    for row in rows:
        normalized = store.normalize_assignment(row)
        if normalized is None or normalized["id"] in assignment_ids:
            return "invalid_response"
        assignment_ids.add(normalized["id"])
    return ""


def _fetch_students(course_id, canvas_get_all):
    return canvas_get_all(
        f"/api/v1/courses/{course_id}/users",
        {"enrollment_type[]": ["student"], "include[]": ["enrollments"],
         "per_page": 100},
    )


def _fetch_sections(course_id, canvas_get_all):
    sections, error = canvas_get_all(
        f"/api/v1/courses/{course_id}/sections", {"per_page": 100})
    if error or not sections:
        return {}, error
    return {str(s["id"]): s.get("name", f"Section {s['id']}") for s in sections}, None


def _fetch_submissions(course_id, canvas_get_all, *, submitted_since=None,
                       graded_since=None, with_history=True,
                       with_comments=False):
    params = {"student_ids[]": "all", "per_page": 100}
    include = []
    if with_history:
        include.append("submission_history")
    if with_comments:
        include.append("submission_comments")
    if include:
        params["include[]"] = include
    if submitted_since:
        params["submitted_since"] = submitted_since
    if graded_since:
        params["graded_since"] = graded_since
    return canvas_get_all(
        f"/api/v1/courses/{course_id}/students/submissions", params, timeout=60)


def sync_assignment_submissions(course_id, assignment_id, *, canvas_get_all,
                                root=None, now=None) -> dict:
    """Refresh one assignment without claiming course-delta coverage.

    This focused-current acquisition deliberately leaves course pass envelopes
    and delta watermarks untouched: one assignment cannot establish freshness
    for the entire course. A transport failure leaves its last-good document
    untouched and returns an in-memory signal for the caller's live fallback.
    """
    blocked = _guard(course_id, root)
    if blocked:
        return blocked
    started = now or store.now_iso()
    try:
        rows, error = canvas_get_all(
            f"/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions",
            {"per_page": 100, "include[]": ["submission_history"]},
        )
    except Exception as exc:
        error = str(exc)
        rows = None
    if error:
        return {"ok": False, "error": error, "error_code": _error_code(error)}
    document = store.merge_submissions(course_id, assignment_id, rows or [],
                                       root=root, attempted_at=started)
    return {"ok": True, "assignment_id": str(assignment_id),
            "submission_rows": len(rows or []),
            "submissions": len(document["submissions"])}


def _group_by_assignment(rows) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for row in rows or []:
        assignment_id = str(row.get("assignment_id") or "")
        if assignment_id:
            grouped.setdefault(assignment_id, []).append(row)
    return grouped


def _guard(course_id, root):
    if store.course_dir(course_id, root) is None:
        return {"ok": False, "error": "workspace not configured"}
    return None


def _is_large_shrink(previous_count: int, new_count: int) -> bool:
    """Empty or >50% shrink vs. the previous committed index (1.0beta slice
    01b completeness gate). ``previous_count == 0`` (first sync, or a rebuilt
    mirror) is never a shrink."""
    if previous_count <= 0:
        return False
    if new_count == 0:
        return True
    return new_count < previous_count * (1 - LARGE_SHRINK_RATIO)


def _commit_assignment_index(course_id, assignments, *, root, attempted_at) -> tuple[dict, dict]:
    """Write the assignment index (1.0beta slice 01b, locked design item 2)
    and prune orphan submission files (item 3), unless the collection just
    underwent a large shrink (item 2's guard) — in which case pruning defers
    to the next pass while the index still commits (deletion is legitimate).

    Membership filtering at read time (``queries.course_submissions`` /
    ``assignment_submissions``, item 1) already hides orphans from every
    aggregate read regardless of whether this call prunes their files, so a
    deferred prune only affects on-disk clutter, never correctness.

    Returns ``(document, diagnostics)`` — sanitized assignment-id-only
    counts/lists (item 4) suitable for the pass summary.
    """
    previous_document = store.read_assignments(course_id, root=root)
    previous_rows = (previous_document or {}).get("assignments") or {}
    previous_ids = set(previous_rows)

    document = store.write_assignments(course_id, assignments, root=root,
                                       attempted_at=attempted_at)
    new_rows = document["assignments"]
    new_ids = set(new_rows)

    added = sorted(new_ids - previous_ids)
    removed = sorted(previous_ids - new_ids)
    changed = sorted(a for a in (new_ids & previous_ids) if new_rows[a] != previous_rows[a])

    large_shrink = _is_large_shrink(len(previous_ids), len(new_ids))
    existing_files = set(store.list_submission_assignment_ids(course_id, root=root))
    orphans_filtered = sorted(existing_files - new_ids)

    pruned: list[str] = []
    if not large_shrink:
        pruned = store.prune_submission_files(course_id, list(new_ids), root=root)

    diagnostics = {
        "added": added,
        "changed": changed,
        "removed": removed,
        "large_shrink": len(removed) if large_shrink else 0,
        "orphans_filtered": orphans_filtered,
        "orphans_pruned": pruned,
    }
    return document, diagnostics


def apply_assignment_collection_receipt(
    course_id,
    receipt,
    *,
    root=None,
    attempted_at=None,
) -> dict:
    """Apply an already-acquired receipt to mirror membership only.

    This deliberately does not establish any sync-pass freshness, reconcile
    submissions, or perform New Quiz work.
    """
    rows, error, complete = receipt
    assignment_error = _assignment_receipt_error(rows, error, complete)
    if assignment_error:
        return {"ok": False, "error": assignment_error}
    document, diagnostics = _commit_assignment_index(
        course_id,
        rows,
        root=root,
        attempted_at=attempted_at or store.now_iso(),
    )
    return {
        "ok": True,
        "assignments": len(document["assignments"]),
        "assignment_changes": diagnostics,
    }


def _skipped_lifecycle_new_quizzes(course_id, *, root=None) -> dict:
    """Return a read-only metadata summary when lifecycle skips the scope."""
    capability = store.read_new_quiz_capability(course_id, root=root)["capability"]
    return {"ok": True, "state": "skipped_lifecycle", "quizzes": 0, "skipped": 0,
            "failures": [], "capability": capability, "skipped_restricted": False,
            "skipped_lifecycle": True, "circuit_opened": False,
            "circuit_cleared": False}


def full_pass(course_id, *, canvas_get_all, canvas_get_all_complete, root=None, now=None,
              bypass_new_quiz_cooldown: bool = False,
              skip_new_quiz_metadata: bool = False) -> dict:
    """Backfill / nightly reconcile: fetch everything first, then rewrite.

    ``bypass_new_quiz_cooldown`` plumbs the manual ``sync_now`` override down
    to the New Quiz metadata capability gate (1.0beta slice 01a) — the
    15-minute heartbeat never passes it."""
    blocked = _guard(course_id, root)
    if blocked:
        return blocked
    started = now or store.now_iso()

    assignments, error, complete = _fetch_assignments(course_id, canvas_get_all_complete)
    assignment_error = _assignment_receipt_error(assignments, error, complete)
    if assignment_error:
        store.record_pass(course_id, "full", ok=False,
                          error_code=assignment_error, attempted_at=started, root=root)
        return {"ok": False, "error": error or assignment_error}
    students, error = _fetch_students(course_id, canvas_get_all)
    if error:
        store.record_pass(course_id, "full", ok=False,
                          error_code=_error_code(error), attempted_at=started, root=root)
        return {"ok": False, "error": error}
    sections, _s_err = _fetch_sections(course_id, canvas_get_all)
    submissions, error = _fetch_submissions(course_id, canvas_get_all,
                                            with_comments=True)
    if error:
        store.record_pass(course_id, "full", ok=False,
                          error_code=_error_code(error), attempted_at=started, root=root)
        return {"ok": False, "error": error}

    document, diagnostics = _commit_assignment_index(
        course_id, assignments, root=root, attempted_at=started)
    store.write_roster(course_id, students, sections, root=root, attempted_at=started)
    grouped = _group_by_assignment(submissions)
    for assignment_id in document["assignments"]:
        store.merge_submissions(course_id, assignment_id,
                                grouped.get(assignment_id, []), root=root,
                                attempted_at=started, replace=True)
    watermark = _overlapped(started)
    store.record_pass(course_id, "roster", ok=True, attempted_at=started, root=root)
    store.record_pass(course_id, "full", ok=True, attempted_at=started,
                      watermarks={"submitted_since": watermark,
                                  "graded_since": watermark},
                      root=root)
    new_quiz_result = (_skipped_lifecycle_new_quizzes(course_id, root=root)
                       if skip_new_quiz_metadata else new_quizzes.sync_metadata(
                           course_id, assignments, canvas_get_all=canvas_get_all,
                           root=root, now=started,
                           bypass_cooldown=bypass_new_quiz_cooldown,
                       ))
    return {"ok": True, "assignments": len(document["assignments"]),
            "students": len(students or []),
            "submission_rows": len(submissions or []),
            "pruned_assignments": diagnostics["orphans_pruned"],
            "assignment_changes": diagnostics,
            "new_quizzes": new_quiz_result}


def delta_pass(course_id, *, canvas_get_all, canvas_get_all_complete, root=None, now=None,
               bypass_new_quiz_cooldown: bool = False,
               skip_new_quiz_metadata: bool = False) -> dict:
    """Incremental pass. Falls back to a full pass when no watermark exists
    yet (first run, or a rebuilt mirror). ``bypass_new_quiz_cooldown`` — see
    ``full_pass``."""
    blocked = _guard(course_id, root)
    if blocked:
        return blocked
    watermarks = store.read_sync(course_id, root=root)["watermarks"]
    if not watermarks["submitted_since"] or not watermarks["graded_since"]:
        return full_pass(course_id, canvas_get_all=canvas_get_all,
                         canvas_get_all_complete=canvas_get_all_complete, root=root, now=now,
                         bypass_new_quiz_cooldown=bypass_new_quiz_cooldown,
                         skip_new_quiz_metadata=skip_new_quiz_metadata)
    started = now or store.now_iso()

    assignments, error, complete = _fetch_assignments(course_id, canvas_get_all_complete)
    assignment_error = _assignment_receipt_error(assignments, error, complete)
    if assignment_error:
        store.record_pass(course_id, "delta", ok=False,
                          error_code=assignment_error, attempted_at=started, root=root)
        return {"ok": False, "error": error or assignment_error}
    submitted, error = _fetch_submissions(
        course_id, canvas_get_all,
        submitted_since=watermarks["submitted_since"], with_history=True)
    if error:
        store.record_pass(course_id, "delta", ok=False,
                          error_code=_error_code(error), attempted_at=started, root=root)
        return {"ok": False, "error": error}
    graded, error = _fetch_submissions(
        course_id, canvas_get_all,
        graded_since=watermarks["graded_since"], with_history=False)
    if error:
        store.record_pass(course_id, "delta", ok=False,
                          error_code=_error_code(error), attempted_at=started, root=root)
        return {"ok": False, "error": error}

    _document, diagnostics = _commit_assignment_index(
        course_id, assignments, root=root, attempted_at=started)
    grouped = _group_by_assignment(list(submitted or []) + list(graded or []))
    for assignment_id, rows in grouped.items():
        store.merge_submissions(course_id, assignment_id, rows, root=root,
                                attempted_at=started, replace=False)
    watermark = _overlapped(started)
    store.record_pass(course_id, "delta", ok=True, attempted_at=started,
                      watermarks={"submitted_since": watermark,
                                  "graded_since": watermark},
                      root=root)
    new_quiz_result = (_skipped_lifecycle_new_quizzes(course_id, root=root)
                       if skip_new_quiz_metadata else new_quizzes.sync_metadata(
                           course_id, assignments, canvas_get_all=canvas_get_all,
                           root=root, now=started,
                           bypass_cooldown=bypass_new_quiz_cooldown,
                       ))
    return {"ok": True, "assignments": len(assignments or []),
            "changed_rows": len(submitted or []) + len(graded or []),
            "touched_assignments": sorted(grouped),
            "assignment_changes": diagnostics,
            "new_quizzes": new_quiz_result}


def roster_pass(course_id, *, canvas_get_all, root=None, now=None) -> dict:
    blocked = _guard(course_id, root)
    if blocked:
        return blocked
    started = now or store.now_iso()
    students, error = _fetch_students(course_id, canvas_get_all)
    if error:
        store.record_pass(course_id, "roster", ok=False,
                          error_code=_error_code(error), attempted_at=started, root=root)
        return {"ok": False, "error": error}
    sections, _s_err = _fetch_sections(course_id, canvas_get_all)
    store.write_roster(course_id, students, sections, root=root, attempted_at=started)
    store.record_pass(course_id, "roster", ok=True, attempted_at=started, root=root)
    return {"ok": True, "students": len(students or [])}
