"""CanvasMirror sync engine — the deterministic passes that keep the mirror fresh.

Three passes, all taking an injected ``canvas_get_all`` (catalog pattern —
this module never imports the Canvas client) and an optional ``now=`` clock
for deterministic tests:

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

# Reuse the catalog's transport-error -> stable-code mapping so diagnostics
# read the same across both mirrors of Canvas data.
from api.course_catalog import _error_code

from . import store


WATERMARK_OVERLAP_MINUTES = 10


def _overlapped(iso_z: str) -> str:
    moment = datetime.strptime(iso_z, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return (moment - timedelta(minutes=WATERMARK_OVERLAP_MINUTES)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _fetch_assignments(course_id, canvas_get_all):
    return canvas_get_all(f"/api/v1/courses/{course_id}/assignments",
                          {"per_page": 100})


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
                       graded_since=None, with_history=True):
    params = {"student_ids[]": "all", "per_page": 100}
    if with_history:
        params["include[]"] = ["submission_history"]
    if submitted_since:
        params["submitted_since"] = submitted_since
    if graded_since:
        params["graded_since"] = graded_since
    return canvas_get_all(
        f"/api/v1/courses/{course_id}/students/submissions", params, timeout=60)


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


def full_pass(course_id, *, canvas_get_all, root=None, now=None) -> dict:
    """Backfill / nightly reconcile: fetch everything first, then rewrite."""
    blocked = _guard(course_id, root)
    if blocked:
        return blocked
    started = now or store.now_iso()

    assignments, error = _fetch_assignments(course_id, canvas_get_all)
    if error:
        store.record_pass(course_id, "full", ok=False,
                          error_code=_error_code(error), attempted_at=started, root=root)
        return {"ok": False, "error": error}
    students, error = _fetch_students(course_id, canvas_get_all)
    if error:
        store.record_pass(course_id, "full", ok=False,
                          error_code=_error_code(error), attempted_at=started, root=root)
        return {"ok": False, "error": error}
    sections, _s_err = _fetch_sections(course_id, canvas_get_all)
    submissions, error = _fetch_submissions(course_id, canvas_get_all)
    if error:
        store.record_pass(course_id, "full", ok=False,
                          error_code=_error_code(error), attempted_at=started, root=root)
        return {"ok": False, "error": error}

    document = store.write_assignments(course_id, assignments, root=root,
                                       attempted_at=started)
    store.write_roster(course_id, students, sections, root=root, attempted_at=started)
    grouped = _group_by_assignment(submissions)
    for assignment_id in document["assignments"]:
        store.merge_submissions(course_id, assignment_id,
                                grouped.get(assignment_id, []), root=root,
                                attempted_at=started, replace=True)
    pruned = store.prune_submission_files(
        course_id, list(document["assignments"]), root=root)
    watermark = _overlapped(started)
    store.record_pass(course_id, "roster", ok=True, attempted_at=started, root=root)
    store.record_pass(course_id, "full", ok=True, attempted_at=started,
                      watermarks={"submitted_since": watermark,
                                  "graded_since": watermark},
                      root=root)
    return {"ok": True, "assignments": len(document["assignments"]),
            "students": len(students or []),
            "submission_rows": len(submissions or []),
            "pruned_assignments": pruned}


def delta_pass(course_id, *, canvas_get_all, root=None, now=None) -> dict:
    """Incremental pass. Falls back to a full pass when no watermark exists
    yet (first run, or a rebuilt mirror)."""
    blocked = _guard(course_id, root)
    if blocked:
        return blocked
    watermarks = store.read_sync(course_id, root=root)["watermarks"]
    if not watermarks["submitted_since"] or not watermarks["graded_since"]:
        return full_pass(course_id, canvas_get_all=canvas_get_all, root=root, now=now)
    started = now or store.now_iso()

    assignments, error = _fetch_assignments(course_id, canvas_get_all)
    if error:
        store.record_pass(course_id, "delta", ok=False,
                          error_code=_error_code(error), attempted_at=started, root=root)
        return {"ok": False, "error": error}
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

    store.write_assignments(course_id, assignments, root=root, attempted_at=started)
    grouped = _group_by_assignment(list(submitted or []) + list(graded or []))
    for assignment_id, rows in grouped.items():
        store.merge_submissions(course_id, assignment_id, rows, root=root,
                                attempted_at=started, replace=False)
    watermark = _overlapped(started)
    store.record_pass(course_id, "delta", ok=True, attempted_at=started,
                      watermarks={"submitted_since": watermark,
                                  "graded_since": watermark},
                      root=root)
    return {"ok": True, "assignments": len(assignments or []),
            "changed_rows": len(submitted or []) + len(graded or []),
            "touched_assignments": sorted(grouped)}


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
