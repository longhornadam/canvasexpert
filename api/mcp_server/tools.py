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
import time
from contextlib import contextmanager

from api import course_scope, gradebook_queries, gradebook_snapshot, roster_service
from api.mirror import queries as mirror_queries
from api.mirror import read_service
from api.mirror import store as mirror_store
from api.webui import config, workspace
from api.webui.canvas_client import _canvas_get_all
from api import feedback_vault
from api.course_catalog import read_catalog

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
_ORIGINAL_ROSTER_FETCH_STUDENTS = roster_service.fetch_students
_ORIGINAL_ROSTER_FETCH_SECTIONS = roster_service.fetch_sections


# ---------------------------------------------------------------------------
# Token-lean payload shaping.
#
# MCP tool results live in the client's context window and are re-sent on
# every following turn, so list data goes out as one {"columns": [...],
# "rows": [[...]]} table instead of repeating JSON keys per row. The privacy
# gate always runs on the dict-row payload BEFORE tabulation — never on the
# tabular form, which the scanner's key-based walk cannot see into.
# ---------------------------------------------------------------------------

_DESCRIPTION_PREVIEW_CHARS = 300
_DEFAULT_MAX_TEXT_CHARS = 2000

_SUBMISSION_COLUMNS = ("pseudonym", "workflow_state", "submitted_at", "late",
                       "missing", "excused", "score", "grade", "text")
_ROSTER_COLUMNS = ("pseudonym", "section_names")
_ASSIGNMENT_COLUMNS = ("id", "title", "due_at", "points_possible",
                       "published", "description_text")
_GRADEBOOK_ASSIGNMENT_COLUMNS = ("id", "title", "due_at", "points", "submitted",
                                 "graded", "missing", "late", "avg_pct")
_GRADEBOOK_STUDENT_COLUMNS = ("pseudonym", "missing", "late", "ungraded", "pct")


def _tabulate(rows: list[dict], columns: tuple[str, ...]) -> dict:
    return {"columns": list(columns),
            "rows": [[row.get(col) for col in columns] for row in rows]}


def _truncate_text(text: str, max_chars: int) -> str:
    """Trim with an explicit marker so the client knows to re-request the
    full text (max_text_chars=0) instead of assuming it saw everything."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[:max_chars] + f" …[truncated {len(text) - max_chars} more chars]"


# ---------------------------------------------------------------------------
# Roster fetch cache.
#
# One MCP server process serves a whole client session, and every student-data
# tool must sync the roster before it can scrub — without a cache, each tool
# call costs a fresh Canvas roster (and sections) round trip. Cache the raw
# FETCH results only (never the vault, never anything on disk) for a few
# minutes. Monkeypatched fetch seams always bypass the cache.
# ---------------------------------------------------------------------------

_ROSTER_CACHE_TTL_SECONDS = 300.0
_roster_fetch_cache: dict[str, tuple[float, list[dict]]] = {}
_section_fetch_cache: dict[str, tuple[float, dict]] = {}


def _cache_safe() -> bool:
    """True only when every roster fetch seam is the real implementation —
    a monkeypatched fetcher's data must never leak across tests via cache."""
    return (
        pseudonym._fetch_students is _ORIGINAL_PSEUDONYM_FETCH_STUDENTS
        and roster_service.fetch_students is _ORIGINAL_ROSTER_FETCH_STUDENTS
        and _fetch_sections is _ORIGINAL_FETCH_SECTIONS
        and roster_service.fetch_sections is _ORIGINAL_ROSTER_FETCH_SECTIONS
    )


def _cached_fetch_students(course_id: str):
    cached = _roster_fetch_cache.get(course_id)
    now = time.monotonic()
    if cached and now - cached[0] < _ROSTER_CACHE_TTL_SECONDS:
        return cached[1], None
    users, err = roster_service.fetch_students(course_id, canvas_get_all=_canvas_get_all)
    if err:
        return None, err
    _roster_fetch_cache[course_id] = (now, users)
    return users, None


def _sync_roster(vault, course_id: str):
    """Fetch (cached) + upsert one course roster so the scrub map covers
    every enrolled student, not just the ones in this payload."""
    if pseudonym._fetch_students is not _ORIGINAL_PSEUDONYM_FETCH_STUDENTS:
        fetcher = lambda cid: pseudonym._fetch_students(cid)
    elif _cache_safe():
        fetcher = _cached_fetch_students
    else:
        fetcher = None
    return roster_service.sync_roster_for_course(
        vault, course_id,
        canvas_get_all=_canvas_get_all,
        fetch_students_override=fetcher,
    )


# ---------------------------------------------------------------------------
# Mirror-first reads.
#
# When the CanvasMirror is fresh enough to serve (and no test seam is
# patched — the seam guard keeps monkeypatched tests on the live path), the
# student-data tools read from disk instead of Canvas: instant, offline-
# tolerant, zero Canvas round trips. Every mirror-served payload is labeled
# with source="mirror" + synced_at so staleness is visible, never silent.
# ---------------------------------------------------------------------------

def _mirror_roster_doc(course_id: str):
    """The typed roster scope (students + sections) when current and
    unseamed, else None. Sections have no dedicated typed scope, so the
    raw roster document is read once more, only after the typed freshness
    check passes, purely to recover the section id -> name map."""
    if not _cache_safe():
        return None
    roster = read_service.private_roster(
        course_id, max_age_hours=mirror_queries._serve_max_age_hours())
    if roster["state"] != "current":
        return None
    document = mirror_store.read_roster(course_id)
    if document is None:
        return None
    return {"students": roster["records"], "sections": document["sections"],
            "last_success_at": roster["last_success_at"]}


def _mirror_submission_bundle(course_id: str, assignment_id: str):
    """``{assignment, rows, roster, synced_at}`` from typed local scopes when
    roster, assignments, and submissions are ALL current, else None (missing
    or stale any one piece falls back to live as one coherent bundle)."""
    if not _cache_safe():
        return None
    if (_assignment is not _ORIGINAL_ASSIGNMENT
            or _assignment_submissions is not _ORIGINAL_ASSIGNMENT_SUBMISSIONS):
        return None
    max_age_hours = mirror_queries._serve_max_age_hours()
    roster = read_service.private_roster(course_id, max_age_hours=max_age_hours)
    assignments = read_service.private_assignments(course_id, max_age_hours=max_age_hours)
    submissions = read_service.private_submissions(course_id, max_age_hours=max_age_hours)
    if not (roster["state"] == "current" and assignments["state"] == "current"
            and submissions["state"] == "current"):
        return None
    assignment_row = next(
        (row for row in assignments["records"] if str(row.get("id")) == str(assignment_id)),
        None)
    if assignment_row is None:
        return None
    rows = [row for row in submissions["records"]
            if str(row.get("assignment_id")) == str(assignment_id)]
    synced_at = min(roster["last_success_at"], assignments["last_success_at"],
                    submissions["last_success_at"])
    return {"assignment": assignment_row, "rows": rows,
            "roster": roster["records"], "synced_at": synced_at}


def _load_sections(course_id: str) -> dict:
    if _fetch_sections is not _ORIGINAL_FETCH_SECTIONS:
        return _fetch_sections(course_id, canvas_get_all=_canvas_get_all)
    if _cache_safe():
        cached = _section_fetch_cache.get(course_id)
        if cached and time.monotonic() - cached[0] < _ROSTER_CACHE_TTL_SECONDS:
            return cached[1]
    section_map = roster_service.fetch_sections(course_id, canvas_get_all=_canvas_get_all)
    if _cache_safe():
        _section_fetch_cache[course_id] = (time.monotonic(), section_map)
    return section_map


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


_VAULT_UNAVAILABLE_ERROR = (
    "Canvas Expert cannot find your workspace, so student data is withheld. "
    "Open Canvas Expert on this computer once (or reconnect from AI Connections), "
    "then try again."
)


class _VaultUnavailable(Exception):
    """Raised when the identity vault directory cannot be resolved."""


def _default_vault() -> feedback_vault.Vault:
    """Mirror ``api/webui/routes/names.py::_vault`` — the one global identity
    vault, keyed by Canvas user id.

    Fails closed when the workspace (and thus the vault directory) cannot be
    resolved, rather than falling back to a stray ``./vault.json``. That stray
    fallback would misplace the re-identification map outside the protected
    workspace and hand out unstable pseudonyms, so student-data tools must
    refuse instead."""
    root = workspace.identity_vault_dir() or workspace.feedback_folder("_vault")
    if not root:
        raise _VaultUnavailable(_VAULT_UNAVAILABLE_ERROR)
    return feedback_vault.Vault(os.path.join(root, "vault.json"))


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


_VAULT_CONFLICT_ERROR = (
    "identity vault conflict detected — resolve in the CanvasExpert web UI "
    "before pseudonymized reads continue"
)


def _vault_conflict_check(vault) -> str | None:
    """Fail-closed guard: a forked vault.json (OneDrive conflict copy) can
    assign a second pseudonym to the same student and silently break scrub
    coverage, so refuse pseudonymized reads until a teacher resolves it in
    the web UI. Test doubles without a ``conflicts()`` method (existing
    ``_vault_factory`` monkeypatches) are treated as conflict-free."""
    conflicts = getattr(vault, "conflicts", None)
    if conflicts is None:
        return None
    if conflicts():
        return _VAULT_CONFLICT_ERROR
    return None


def _open_vault():
    """Open the identity vault, failing closed if it is unavailable or forked.

    Returns ``(vault, None)`` on success or ``(None, error)`` for the tool to
    return verbatim."""
    try:
        vault = _vault_factory()
    except _VaultUnavailable as error:
        return None, str(error)
    return vault, _vault_conflict_check(vault)


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


def get_course_assignments(course_id: str, full_descriptions: bool = False) -> dict:
    """Assignment metadata from the local course catalog (disk-only, no live
    Canvas fallback — refresh the catalog from the web UI first). No student
    data — no safety gate. Descriptions are trimmed to a preview unless
    ``full_descriptions`` is set; assignments go out as a {columns, rows}
    table."""
    err = _course_gate_check(course_id)
    if err:
        return {"ok": False, "error": err}

    read_result = read_catalog(course_id)
    scope = read_service.catalog_assignments(
        course_id, catalog_reader=lambda _course_id: read_result)
    if scope["source"] == "none":
        return {
            "ok": False,
            "error": ("No local course catalog found for this course. Refresh "
                      "the catalog from the CanvasExpert web UI, then try again."),
        }

    description_chars = 0 if full_descriptions else _DESCRIPTION_PREVIEW_CHARS
    assignments = [
        {
            "id": a.get("id"),
            "title": a.get("name", ""),
            "description_text": _truncate_text(a.get("description_text", ""),
                                               description_chars),
            "due_at": a.get("due_at", ""),
            "points_possible": a.get("points_possible"),
            "published": a.get("published", True),
        }
        for a in scope["records"]
    ]
    return {
        "ok": True,
        "course_id": str((read_result.get("catalog") or {}).get("course_id") or course_id),
        "course_name": str((read_result.get("catalog") or {}).get("course_name") or ""),
        "assignments": _tabulate(assignments, _ASSIGNMENT_COLUMNS),
    }


def get_roster(course_id: str) -> dict:
    """Current roster as a {columns, rows} table of (pseudonym,
    section_names), sorted by pseudonym. Mirror-first; pseudonymized through
    the identity vault; gated by the outbound safety scan before tabulation."""
    err = _course_gate_check(course_id)
    if err:
        return {"ok": False, "error": err}

    vault, vault_err = _open_vault()
    if vault_err:
        return {"ok": False, "error": vault_err}

    mirror_doc = _mirror_roster_doc(course_id)
    with _vault_transaction(vault):
        if mirror_doc is not None:
            users = mirror_doc["students"]
            roster_service.upsert_roster(vault, users)
            section_map = mirror_doc["sections"]
            source, synced_at = "mirror", mirror_doc["last_success_at"]
        else:
            users, fetch_err = _sync_roster(vault, course_id)
            if fetch_err:
                return {"ok": False, "error": fetch_err}
            section_map = _load_sections(course_id)
            source, synced_at = "canvas", ""
        roster = pseudonym.pseudonymize_roster(vault, users, section_map)
        result = pseudonym.gate(
            {"roster": roster, "source": source, "synced_at": synced_at}, vault)
    if result.get("ok"):
        result["roster"] = _tabulate(result["roster"], _ROSTER_COLUMNS)
    return result


def get_submissions(course_id: str, assignment_id: str,
                    include_text: bool = True, pseudonyms: str = "",
                    max_text_chars: int = _DEFAULT_MAX_TEXT_CHARS) -> dict:
    """One assignment's submissions, pseudonymized and scrubbed, as
    ``{assignment: {...}, submissions: {columns, rows}}``. ``pseudonyms``
    (comma-separated) narrows to specific students; ``include_text=False``
    drops the text column; text is trimmed to ``max_text_chars`` (0 = full).
    Attachments are never included. Gated by the outbound safety scan."""
    err = _course_gate_check(course_id)
    if err:
        return {"ok": False, "error": err}

    vault, vault_err = _open_vault()
    if vault_err:
        return {"ok": False, "error": vault_err}

    bundle = _mirror_submission_bundle(course_id, assignment_id)
    # Sync the full roster first so the scrub map covers every enrolled
    # student, not just the ones who submitted this assignment.
    with _vault_transaction(vault):
        if bundle is not None:
            roster_service.upsert_roster(vault, bundle["roster"])
            assignment, subs = bundle["assignment"], bundle["rows"]
            source, synced_at = "mirror", bundle["synced_at"]
        else:
            _, fetch_err = _sync_roster(vault, course_id)
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
            source, synced_at = "canvas", ""

        rows = pseudonym.pseudonymize_submission_rows(vault, subs)
        wanted = {p.strip().casefold() for p in pseudonyms.split(",") if p.strip()}
        if wanted:
            rows = [r for r in rows if r["pseudonym"].casefold() in wanted]
        # Trim/drop text BEFORE the gate so the scan covers exactly the bytes
        # that leave the machine.
        for row in rows:
            if include_text:
                row["text"] = _truncate_text(row["text"], max_text_chars)
            else:
                row.pop("text", None)

        payload = {
            "assignment": {
                "id": assignment.get("id"),
                "title": assignment.get("name", ""),
                "points_possible": assignment.get("points_possible"),
                "due_at": assignment.get("due_at", ""),
            },
            "submissions": rows,
            "source": source,
            "synced_at": synced_at,
        }
        result = pseudonym.gate(payload, vault)
    if result.get("ok"):
        columns = (_SUBMISSION_COLUMNS if include_text
                   else tuple(c for c in _SUBMISSION_COLUMNS if c != "text"))
        result["submissions"] = _tabulate(result["submissions"], columns)
    return result


def get_gradebook_snapshot(course_id: str) -> dict:
    """Whole-course grading snapshot, pseudonymized: per-assignment stats
    (``title`` instead of ``name``, no ``html_url``) and per-student stats
    (``pseudonym`` instead of a name), each as a {columns, rows} table.
    Gated by the outbound safety scan before tabulation."""
    err = _course_gate_check(course_id)
    if err:
        return {"ok": False, "error": err}

    vault, vault_err = _open_vault()
    if vault_err:
        return {"ok": False, "error": vault_err}

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
        "source": snapshot.get("source", "canvas"),
        "synced_at": snapshot.get("synced_at", ""),
        "assignments": assignment_rows,
        "students": [],
    }
    with _vault_transaction(vault):
        roster_service.upsert_roster(vault, [
            {"id": row.get("user_id"), "name": row.get("name", "")}
            for row in students
        ])
        payload["students"] = pseudonym.pseudonymize_gradebook_rows(vault, snapshot["students"])
        result = pseudonym.gate(payload, vault)
    if result.get("ok"):
        result["assignments"] = _tabulate(result["assignments"], _GRADEBOOK_ASSIGNMENT_COLUMNS)
        result["students"] = _tabulate(result["students"], _GRADEBOOK_STUDENT_COLUMNS)
    return result
