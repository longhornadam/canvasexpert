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

try:  # pragma: no cover - exercised via one or the other branch
    from webui import config, workspace
    from webui.canvas_client import _canvas_get_all
    from webui.routes.gradebook_common import (
        _assignment,
        _assignment_submissions,
        _course_assignments,
        _course_students,
        _course_submissions,
    )
    from webui.routes.gradebook_snapshot import build_snapshot
    from webui.routes.names import _upsert_roster
    from webui.routes.roster_canvas import fetch_sections as _fetch_sections
except ModuleNotFoundError:  # package/test context
    from api.webui import config, workspace
    from api.webui.canvas_client import _canvas_get_all
    from api.webui.routes.gradebook_common import (
        _assignment,
        _assignment_submissions,
        _course_assignments,
        _course_students,
        _course_submissions,
    )
    from api.webui.routes.gradebook_snapshot import build_snapshot
    from api.webui.routes.names import _upsert_roster
    from api.webui.routes.roster_canvas import fetch_sections as _fetch_sections

try:  # pragma: no cover - exercised via one or the other branch
    import feedback_vault
    from course_catalog import public_projection, read_catalog
except ModuleNotFoundError:  # package/test context
    from api import feedback_vault
    from api.course_catalog import public_projection, read_catalog

from . import pseudonym


def _default_vault() -> feedback_vault.Vault:
    """Mirror ``api/webui/routes/names.py::_vault`` — the one global identity
    vault, keyed by Canvas user id."""
    root = workspace.identity_vault_dir() or workspace.feedback_folder("_vault")
    return feedback_vault.Vault(os.path.join(root or ".", "vault.json"))


# Bound to a module-level name so tests can point it at a tmp_path vault.
_vault_factory = _default_vault


def _course_gate_check(course_id: str) -> str | None:
    """Current-course scope check, same as the web UI. Returns an error
    string if ``course_id`` is not an active (Current) course, else None."""
    allowed = {str(c.get("id", "")) for c in config.active_courses()}
    if str(course_id) not in allowed:
        return f"course_id '{course_id}' is not a Current course in CanvasExpert."
    return None


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
    users, fetch_err = pseudonym.sync_vault_for_course(vault, course_id)
    if fetch_err:
        return {"ok": False, "error": fetch_err}

    section_map = _fetch_sections(course_id, canvas_get_all=_canvas_get_all)
    roster = pseudonym.pseudonymize_roster(vault, users, section_map)
    vault.save()
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
    _, fetch_err = pseudonym.sync_vault_for_course(vault, course_id)
    if fetch_err:
        return {"ok": False, "error": fetch_err}

    assignment, a_err = _assignment(course_id, assignment_id)
    if a_err:
        return {"ok": False, "error": a_err}
    subs, s_err = _assignment_submissions(course_id, assignment_id)
    if s_err:
        return {"ok": False, "error": s_err}

    rows = pseudonym.pseudonymize_submission_rows(vault, subs)
    vault.save()
    payload = {
        "assignment": {
            "id": assignment.get("id"),
            "title": assignment.get("name", ""),
            "points_possible": assignment.get("points_possible"),
            "due_at": assignment.get("due_at", ""),
        },
        "submissions": rows,
    }
    return pseudonym.gate(payload, vault)


def get_gradebook_snapshot(course_id: str) -> dict:
    """Whole-course grading snapshot, pseudonymized: per-assignment stats
    (``title`` instead of ``name``, no ``html_url``) and per-student stats
    (``pseudonym`` instead of a name). Gated by the outbound safety scan."""
    err = _course_gate_check(course_id)
    if err:
        return {"ok": False, "error": err}

    students, s_err = _course_students(course_id)
    if s_err:
        return {"ok": False, "error": s_err}
    assignments, a_err = _course_assignments(course_id)
    if a_err:
        return {"ok": False, "error": a_err}
    subs, sub_err = _course_submissions(course_id)
    if sub_err:
        return {"ok": False, "error": sub_err}

    snapshot = build_snapshot(students, assignments, subs)

    vault = _vault_factory()
    _upsert_roster(vault, students)
    student_rows = pseudonym.pseudonymize_gradebook_rows(vault, snapshot["students"])
    vault.save()

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
        "students": student_rows,
    }
    return pseudonym.gate(payload, vault)
