"""Plain, testable implementations of the 5 read-only MCP tools.

Every function returns a ``{"ok": ...}`` dict and never raises — that keeps
errors structured for the LLM and matches the rest of the app's route style.
Fetchers and the vault factory are bound to module-level names so tests can
monkeypatch them without touching the real Canvas API or identity vault
(same pattern as ``api/tests/test_gradebook_routes.py``).

Every ``course_id`` tool gates on ``config.active_courses()`` — the same
Current-course scope the web UI uses. ``list_courses`` is the only tool with
no ``course_id`` and no student data, so it skips both the course gate and
the outbound safety gate.
"""
from __future__ import annotations

import os
from contextlib import contextmanager

from api import course_scope, gradebook_queries, gradebook_snapshot, roster_service
from api.webui import config, workspace
from api.webui.canvas_client import _canvas_get_all
from api import feedback_vault
from api.course_catalog import public_projection, read_catalog

from . import pseudonym


# Compatibility seams retained for existing route-style tests; the bound
# implementations all live in root-level shared use-case modules.
_course_students = gradebook_queries.course_students
_course_assignments = gradebook_queries.course_assignments
_course_submissions = gradebook_queries.course_submissions
_assignment = gradebook_queries.assignment
_assignment_submissions = gradebook_queries.assignment_submissions
_fetch_sections = roster_service.fetch_sections
_ORIGINAL_COURSE_STUDENTS = _course_students
_ORIGINAL_COURSE_ASSIGNMENTS = _course_assignments
_ORIGINAL_COURSE_SUBMISSIONS = _course_submissions
_ORIGINAL_ASSIGNMENT = _assignment
_ORIGINAL_ASSIGNMENT_SUBMISSIONS = _assignment_submissions
_ORIGINAL_FETCH_SECTIONS = _fetch_sections
_ORIGINAL_PSEUDONYM_FETCH_STUDENTS = pseudonym._fetch_students


def _load_snapshot(course_id: str):
    if (
        _course_students is _ORIGINAL_COURSE_STUDENTS
        and _course_assignments is _ORIGINAL_COURSE_ASSIGNMENTS
        and _course_submissions is _ORIGINAL_COURSE_SUBMISSIONS
    ):
        return gradebook_snapshot.load_snapshot(course_id)
    queries = type("McpQueries", (), {
        "course_students": staticmethod(_course_students),
        "course_assignments": staticmethod(_course_assignments),
        "course_submissions": staticmethod(_course_submissions),
    })
    return gradebook_snapshot.load_snapshot(course_id, queries=queries)


def _default_vault() -> feedback_vault.Vault:
    """Mirror ``api/webui/routes/names.py::_vault`` — the one global identity
    vault, keyed by Canvas user id."""
    root = workspace.identity_vault_dir() or workspace.feedback_folder("_vault")
    return feedback_vault.Vault(os.path.join(root or ".", "vault.json"))


# Bound to a module-level name so tests can point it at a tmp_path vault.
_vault_factory = _default_vault


@contextmanager
def _vault_transaction(vault):
    """Use the durable vault transaction, with a narrow test-double fallback."""
    transaction = getattr(vault, "transaction", None)
    if transaction is not None:
        with transaction():
            yield vault
        return
    try:
        yield vault
    finally:
        save = getattr(vault, "save", None)
        if save is not None:
            save()


def _course_gate_check(course_id: str) -> str | None:
    """Current-course scope check, same as the web UI. Returns an error
    string if ``course_id`` is not an active (Current) course, else None."""
    return course_scope.current_course_error(course_id, config.active_courses())


def list_courses() -> dict:
    """All saved courses (Current + Previous). No Canvas call, no student
    data — no course gate, no safety gate."""
    courses = config.saved_courses()
    return {
        "ok": True,
        "courses": [
            {
                "course_id": str(c.get("id", "")),
                "course_name": str(c.get("nickname") or c.get("name") or ""),
                "active": bool(c.get("active", True)),
            }
            for c in courses
        ],
    }


def get_course_assignments(course_id: str) -> dict:
    """Assignment metadata from the local course catalog (disk-only, no live
    Canvas fallback — refresh the catalog from the web UI first). No student
    data — no safety gate."""
    err = _course_gate_check(course_id)
    if err:
        return {"ok": False, "error": err}

    projection = public_projection(read_catalog(course_id), course_id=course_id)
    if not projection.get("available"):
        return {
            "ok": False,
            "error": ("No local course catalog found for this course. Refresh "
                      "the catalog from the CanvasExpert web UI, then try again."),
        }

    assignments = [
        {
            "id": a.get("id"),
            "title": a.get("name", ""),
            "description_text": a.get("description_text", ""),
            "due_at": a.get("due_at", ""),
            "points_possible": a.get("points_possible"),
            "published": a.get("published", True),
        }
        for a in projection.get("assignments", [])
    ]
    return {
        "ok": True,
        "course_id": str(projection.get("course_id") or course_id),
        "course_name": projection.get("course_name", ""),
        "assignments": assignments,
    }


def get_roster(course_id: str) -> dict:
    """Current roster: ``[{pseudonym, section_names}]``, sorted by pseudonym.
    Pseudonymized through the identity vault; gated by the outbound safety
    scan before it is returned."""
    err = _course_gate_check(course_id)
    if err:
        return {"ok": False, "error": err}

    vault = _vault_factory()
    with _vault_transaction(vault):
        fetch_override = None
        if pseudonym._fetch_students is not _ORIGINAL_PSEUDONYM_FETCH_STUDENTS:
            fetch_override = lambda cid: pseudonym._fetch_students(cid)
        users, fetch_err = roster_service.sync_roster_for_course(
            vault,
            course_id,
            canvas_get_all=_canvas_get_all,
            fetch_students_override=fetch_override,
        )
        if fetch_err:
            return {"ok": False, "error": fetch_err}
        if _fetch_sections is _ORIGINAL_FETCH_SECTIONS:
            section_map = roster_service.fetch_sections(course_id, canvas_get_all=_canvas_get_all)
        else:
            section_map = _fetch_sections(course_id, canvas_get_all=_canvas_get_all)
        roster = pseudonym.pseudonymize_roster(vault, users, section_map)
        return pseudonym.gate({"roster": roster}, vault)


def get_submissions(course_id: str, assignment_id: str) -> dict:
    """One assignment's submissions, pseudonymized and scrubbed:
    ``{assignment: {id, title, points_possible, due_at}, submissions: [...]}``.
    Attachments are never included. Gated by the outbound safety scan."""
    err = _course_gate_check(course_id)
    if err:
        return {"ok": False, "error": err}

    vault = _vault_factory()
    # Sync the full roster first so the scrub map covers every enrolled
    # student, not just the ones who submitted this assignment.
    with _vault_transaction(vault):
        fetch_override = None
        if pseudonym._fetch_students is not _ORIGINAL_PSEUDONYM_FETCH_STUDENTS:
            fetch_override = lambda cid: pseudonym._fetch_students(cid)
        _, fetch_err = roster_service.sync_roster_for_course(
            vault,
            course_id,
            canvas_get_all=_canvas_get_all,
            fetch_students_override=fetch_override,
        )
        if fetch_err:
            return {"ok": False, "error": fetch_err}
        assignment_reader = (
            gradebook_queries.assignment
            if _assignment is _ORIGINAL_ASSIGNMENT else _assignment
        )
        submission_reader = (
            gradebook_queries.assignment_submissions
            if _assignment_submissions is _ORIGINAL_ASSIGNMENT_SUBMISSIONS
            else _assignment_submissions
        )
        assignment, a_err = assignment_reader(course_id, assignment_id)
        if a_err:
            return {"ok": False, "error": a_err}
        subs, s_err = submission_reader(course_id, assignment_id)
        if s_err:
            return {"ok": False, "error": s_err}

        payload = {
            "assignment": {
                "id": assignment.get("id"),
                "title": assignment.get("name", ""),
                "points_possible": assignment.get("points_possible"),
                "due_at": assignment.get("due_at", ""),
            },
            "submissions": [],
        }
        payload["submissions"] = pseudonym.pseudonymize_submission_rows(vault, subs)
        return pseudonym.gate(payload, vault)


def get_gradebook_snapshot(course_id: str) -> dict:
    """Whole-course grading snapshot, pseudonymized: per-assignment stats
    (``title`` instead of ``name``, no ``html_url``) and per-student stats
    (``pseudonym`` instead of a name). Gated by the outbound safety scan."""
    err = _course_gate_check(course_id)
    if err:
        return {"ok": False, "error": err}

    snapshot, snapshot_error = _load_snapshot(course_id)
    if snapshot_error:
        return {"ok": False, "error": snapshot_error}
    students = snapshot.get("students") or []

    assignment_rows = []
    for a in snapshot["assignments"]:
        row = {k: v for k, v in a.items() if k not in ("name", "html_url")}
        row["title"] = a.get("name", "")
        assignment_rows.append(row)

    payload = {
        "class_avg": snapshot["class_avg"],
        "student_count": snapshot["student_count"],
        "total_missing": snapshot["total_missing"],
        "total_ungraded": snapshot["total_ungraded"],
        "assignments": assignment_rows,
        "students": [],
    }
    vault = _vault_factory()
    with _vault_transaction(vault):
        roster_service.upsert_roster(vault, [
            {"id": row.get("user_id"), "name": row.get("name", "")}
            for row in students
        ])
        payload["students"] = pseudonym.pseudonymize_gradebook_rows(vault, snapshot["students"])
        return pseudonym.gate(payload, vault)
