"""Plain, testable implementations of the 13 MCP tools.

Every function returns a ``{"ok": ...}`` dict and never raises — that keeps
errors structured for the LLM and matches the rest of the app's route style.
Fetchers and the vault factory are bound to module-level names so tests can
monkeypatch them without touching the real Canvas API or identity vault
(same pattern as ``api/tests/test_gradebook_routes.py``).

Every ``course_id`` tool gates on ``config.active_courses()`` — the same
Current-course scope the web UI uses. ``list_courses``,
``get_authoring_contract``, ``get_product_guide``, and
``list_staged_content`` are the only tools with no ``course_id`` and no
student data, so they skip both the course gate and the outbound safety gate.
``get_writing_history`` breaks that pairing on purpose: it has no
``course_id`` either (the daily-writing store has no course concept), but it
is student data, so it still runs the identity vault and the outbound safety
gate.

Strict mirror-only law: get_roster, get_submissions, and
get_gradebook_snapshot serve ONLY from the local CanvasMirror and refuse
(rather than falling back to a live Canvas fetch) when it isn't fresh
enough. refresh_mirror is the assistant's only way to move that forward —
it triggers Canvas Expert's own sync engine and reports freshness, never
Canvas data, keeping the AI's whole path to Canvas indirect. get_writing_history
is not mirror-backed (the daily-writing store is not Canvas data at all), so
no staleness refusal applies to it."""
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import date, timedelta

from api import course_scope, feedback_scrub, gradebook_queries, gradebook_snapshot, roster_context, roster_service
from api.mirror import queries as mirror_queries
from api.mirror import read_service
from api.mirror import store as mirror_store
from api.webui import config, mirror_service, workspace
from api.webui.deps import REPO_ROOT
from api.webui import deps
from api import feedback_vault
from api.course_catalog import read_catalog
from api import runtime_paths
from api.dailywriting import projection as dailywriting_projection
from api.dailywriting.store.identity import IdentityError
from api.dailywriting.store.repo import Repository as DailyWritingRepository
from api.dailywriting.store.repo import StoreError as DailyWritingStoreError

from . import pseudonym


# Compatibility seams retained for existing route-style tests; the bound
# implementations all live in root-level shared use-case modules.
_assignment = gradebook_queries.assignment
_assignment_submissions = gradebook_queries.assignment_submissions
_fetch_sections = roster_service.fetch_sections
_ORIGINAL_ASSIGNMENT = _assignment
_ORIGINAL_ASSIGNMENT_SUBMISSIONS = _assignment_submissions
_ORIGINAL_FETCH_SECTIONS = _fetch_sections
_ORIGINAL_PSEUDONYM_FETCH_STUDENTS = pseudonym._fetch_students
_ORIGINAL_ROSTER_FETCH_STUDENTS = roster_service.fetch_students
_ORIGINAL_ROSTER_FETCH_SECTIONS = roster_service.fetch_sections

# Bound seams for the assistant-invokable refresh tool, so tests can point
# these at a fake coordinator without starting the real background workers.
_enqueue_sync = mirror_service.enqueue_sync
_wait_for_plan = mirror_service.wait_for_plan

# Bound so tests can point get_writing_history at a tmp_path store with a
# fixture MappingResolver instead of the real workspace + identity vault
# (same reason _vault_factory exists). `pseudonym.gate` is bound too: the
# tool's own parameter is named `pseudonym` (locked by the brief, matching
# the read pattern), which would otherwise shadow the `pseudonym` module
# inside that one function.
_dailywriting_repository_factory = DailyWritingRepository.default
_pseudonym_gate = pseudonym.gate


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
_MODULE_COLUMNS = ("id", "name", "position", "item_count")
_MODULE_COLUMNS_WITH_PUBLISHED = ("id", "name", "position", "published", "item_count")
_MODULE_ITEM_COLUMNS = ("id", "type", "title", "position")
_STAGED_CONTENT_COLUMNS = ("kind", "label")


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
# Fetch-seam detection.
#
# Strict mirror-only law: the student-data tools never call live Canvas, so
# there is no fetch cache to protect here anymore. ``_cache_safe`` survives
# purely as the seam guard the mirror-first helpers below use to refuse
# serving mirror data out from under a test that has monkeypatched one of
# these fetchers for an unrelated purpose.
# ---------------------------------------------------------------------------


def _cache_safe() -> bool:
    """True only when every roster fetch seam is the real implementation."""
    return (
        pseudonym._fetch_students is _ORIGINAL_PSEUDONYM_FETCH_STUDENTS
        and roster_service.fetch_students is _ORIGINAL_ROSTER_FETCH_STUDENTS
        and _fetch_sections is _ORIGINAL_FETCH_SECTIONS
        and roster_service.fetch_sections is _ORIGINAL_ROSTER_FETCH_SECTIONS
    )


# ---------------------------------------------------------------------------
# Mirror-only reads.
#
# The student-data tools serve ONLY from the local CanvasMirror, never live
# Canvas: instant, offline-tolerant, zero Canvas round trips, and the AI's
# path to Canvas always stays indirect (through Canvas Expert's own sync
# engine, never a direct relay). When the mirror isn't fresh enough to serve
# (or a test seam is patched — the seam guard refuses rather than silently
# reading disk out from under it), these helpers return None so the caller
# refuses instead of fetching live. Mirror-only payloads are labeled
# source="mirror" + synced_at; a caller that joins private local context must
# label that boundary explicitly, so staleness is visible and never silent.
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
    """``({assignment, rows, roster, synced_at}, None)`` from typed local
    scopes when roster, assignments, and submissions are ALL current and
    ``assignment_id`` is one of them. ``(None, None)`` means the mirror
    itself isn't fresh enough to serve (missing or stale any one piece,
    including the seam-guard case); ``(None, message)`` means the mirror IS
    fresh but no such assignment exists in this course — a distinct,
    non-staleness error worth reporting verbatim."""
    if not _cache_safe():
        return None, None
    if (_assignment is not _ORIGINAL_ASSIGNMENT
            or _assignment_submissions is not _ORIGINAL_ASSIGNMENT_SUBMISSIONS):
        return None, None
    max_age_hours = mirror_queries._serve_max_age_hours()
    roster = read_service.private_roster(course_id, max_age_hours=max_age_hours)
    assignments = read_service.private_assignments(course_id, max_age_hours=max_age_hours)
    submissions = read_service.private_submissions(course_id, max_age_hours=max_age_hours)
    if not (roster["state"] == "current" and assignments["state"] == "current"
            and submissions["state"] == "current"):
        return None, None
    assignment_row = next(
        (row for row in assignments["records"] if str(row.get("id")) == str(assignment_id)),
        None)
    if assignment_row is None:
        return None, "No such assignment in this course's local catalog."
    rows = [row for row in submissions["records"]
            if str(row.get("assignment_id")) == str(assignment_id)]
    synced_at = min(roster["last_success_at"], assignments["last_success_at"],
                    submissions["last_success_at"])
    return {"assignment": assignment_row, "rows": rows,
            "roster": roster["records"], "synced_at": synced_at}, None


def _load_snapshot(course_id: str):
    """``(snapshot, None)`` from the CanvasMirror ONLY when it's fresh enough
    to serve the whole gradebook (roster + assignments + submissions), else
    ``(None, error)``. Never falls back to live Canvas — unlike the shared
    ``gradebook_snapshot.load_snapshot`` the web UI's own gradebook route
    uses, which keeps that live fallback for its own grading flows."""
    namespace, synced_at = mirror_queries.snapshot_queries(course_id)
    if namespace is None:
        return None, _MIRROR_UNAVAILABLE_SNAPSHOT_ERROR
    snapshot, error = gradebook_snapshot.load_snapshot(course_id, queries=namespace)
    if error:
        return None, error
    snapshot["source"] = "mirror"
    snapshot["synced_at"] = synced_at
    return snapshot, None


_VAULT_UNAVAILABLE_ERROR = (
    "Canvas Expert cannot find your workspace, so student data is withheld. "
    "Open Canvas Expert on this computer once (or reconnect from the CanvasAgent page), "
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
    root = workspace.identity_vault_dir()
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
                "lifecycle": mirror_store.read_course_context(
                    str(c.get("id", ""))).get("lifecycle", "unknown"),
            }
            for c in courses
        ],
    }


_SECTION_COLUMNS = ("section_id", "section_name")


def list_sections(course_id: str) -> dict:
    """Section names from the local CanvasMirror roster (disk-only, no live
    Canvas fallback). No student data — no vault, no safety gate. Returns
    a {columns, rows} table of (section_id, section_name). Call this before
    get_seating_context to discover valid section_name values."""
    err = _course_gate_check(course_id)
    if err:
        return {"ok": False, "error": err}

    document = mirror_store.read_roster(course_id)
    if document is None:
        return {
            "ok": False,
            "error": _MIRROR_UNAVAILABLE_ROSTER_ERROR,
        }

    sections = document.get("sections", {})
    rows = [
        {"section_id": str(sid), "section_name": str(name)}
        for sid, name in sections.items()
    ]
    return {
        "ok": True,
        "course_id": course_id,
        "sections": _tabulate(rows, _SECTION_COLUMNS),
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


def get_modules(course_id: str, include_items: bool = False) -> dict:
    """Module structure from the local course catalog (disk-only, no live
    Canvas fallback — refresh the catalog from the web UI first). No student
    data — no vault, no safety gate. Staleness is labeled (source, synced_at,
    state), never refused, since modules are structural, not student data.
    Modules go out as a {columns, rows} table; include_items nests each
    module's items as their own {columns, rows} table. ``published`` is
    included only when the catalog record actually carries it."""
    err = _course_gate_check(course_id)
    if err:
        return {"ok": False, "error": err}

    read_result = read_catalog(course_id)
    # Age-gate the stored catalog against the same mirror serve-age window
    # used elsewhere, so "current" means fresh, not just last-refreshed-ever;
    # a stale catalog is still returned in full, only relabeled "stale".
    scope = read_service.catalog_modules(
        course_id, catalog_reader=lambda _course_id: read_result,
        max_age_hours=mirror_queries._serve_max_age_hours())
    if scope["source"] == "none":
        return {
            "ok": False,
            "error": ("No local course catalog found for this course. Refresh "
                      "the catalog from the CanvasExpert web UI, then try again."),
        }

    records = scope["records"]
    # Distinguish "never successfully cataloged" (state=unavailable, no
    # last_success_at) from "cataloged but has no modules" (state=current/stale
    # with empty records), since both produce an empty modules list.
    never_cataloged = (
        scope["state"] == "unavailable"
        and not scope.get("last_success_at")
    )
    modules_state_detail = "never_cataloged" if never_cataloged else "cataloged"
    has_published = any("published" in module for module in records)
    columns = _MODULE_COLUMNS_WITH_PUBLISHED if has_published else _MODULE_COLUMNS
    if include_items:
        columns = columns + ("items",)

    modules = []
    for module in records:
        row = {
            "id": module.get("id"),
            "name": module.get("name", ""),
            "position": module.get("position"),
            "item_count": len(module.get("items") or []),
        }
        if has_published:
            row["published"] = module.get("published")
        if include_items:
            items = [
                {
                    "id": item.get("id"),
                    "type": item.get("type", ""),
                    "title": item.get("title", ""),
                    "position": item.get("position"),
                }
                for item in (module.get("items") or [])
            ]
            row["items"] = _tabulate(items, _MODULE_ITEM_COLUMNS)
        modules.append(row)

    return {
        "ok": True,
        "course_id": str((read_result.get("catalog") or {}).get("course_id") or course_id),
        "course_name": str((read_result.get("catalog") or {}).get("course_name") or ""),
        "modules": _tabulate(modules, columns),
        "source": scope["source"],
        "synced_at": scope["last_success_at"],
        "state": scope["state"],
        "modules_state_detail": modules_state_detail,
    }


_CONTRACT_FILES = {
    "quiz": "Author a Quiz (QuizForge).txt",
    "assignment": "Author an Assignment (AssignmentForge).txt",
    "page": "Author a Page (PageForge).txt",
    "rubric": "Author a Rubric (RubricForge).txt",
}
_GLASS_CONTRACT_FILES = {
    "glass_pane": "Glass Pane contract.txt",
    "glass_scene": "Glass Scene contract.txt",
}

# Product knowledge the tool surface does not imply. An assistant that only
# sees the tool list cannot tell that Writing Timeline exists, or that every
# writing assignment is tracked or not tracked — so it guesses, or worse,
# tells the teacher a feature they use every week isn't real. These are the
# same canonical files the web UI hands out for pasting into a chat-only
# assistant, so connected and pasted assistants read one text, not two.
_GUIDE_FILES = {
    "overview": "START HERE - CanvasAgent.txt",
    "writing_timeline": "Writing Timeline (tracked assignments).txt",
    "writing_record": "Writing Record (longitudinal writing history).txt",
}
_DEFAULT_GUIDE_TOPIC = "overview"


def _read_authoring_doc(filename: str, label: str) -> tuple[str | None, str | None]:
    """Read one file from ``api/default_docs/AI Authoring/`` verbatim — the same
    on-disk source ``/api/download-contract`` serves, so each document lives in
    exactly one place. Returns ``(text, None)`` or ``(None, error)``."""
    path = os.path.join(REPO_ROOT, "api", "default_docs", "AI Authoring", filename)
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read(), None
    except OSError as error:
        return None, f"Could not read the {label}: {error}"


def _staging_appendix(kind: str) -> str:
    """A short "how to stage this for the teacher" section appended to the
    contract an assistant pulls. Kept here rather than in the shared
    ``api/default_docs/AI Authoring/`` files so the web UI's own
    download-contract stays the pure envelope format, while an MCP assistant
    that authors a draft learns where to drop it and how to mark it complete.
    The detailed steps ride this response, so they cost context only when
    authoring."""
    folder = runtime_paths.inbox_folder(kind)
    where = str(folder) if folder else (
        f"the {kind.capitalize()} Inbox folder in the Canvas Expert workspace")
    return (
        "\n\n---\n\n"
        "## Staging this for the teacher\n\n"
        "Do not push to Canvas yourself. When the draft is ready, stage it for "
        "the teacher to review and push:\n\n"
        f"1. Write the completed envelope to a `.txt` file in this kind's Inbox "
        f"folder:\n   `{where}`\n"
        "2. Write a sibling marker file named the same with `.done` added (for "
        "example `my-quiz.txt` and `my-quiz.txt.done`). Its only contents are "
        "the draft's size in bytes, measured from the file on disk after you "
        "write it. Do not use the length of the text you generated: a text-mode "
        "write can turn each line ending into two bytes, so a count taken "
        "beforehand will be wrong and the draft is held back until the sizes "
        "agree.\n"
        "3. Tell the teacher it is staged. It appears under \"Staged by your "
        "assistant (pending review)\" in the matching Canvas Expert push tab, "
        "where they validate and push it. You never write to Canvas.\n"
    )


def get_authoring_contract(kind: str) -> dict:
    """Return one canonical Forge or Glass authoring contract.

    Forge contracts come from ``api/default_docs/AI Authoring/`` and receive
    the Forge-only staging appendix. ``glass_pane`` and ``glass_scene`` come
    directly from ``api/default_docs/Glass/`` with no staging appendix because
    their only authoring path is a pending local Glass draft. No course_id,
    student data, vault, or safety gate applies.
    """
    if kind in _GLASS_CONTRACT_FILES:
        path = os.path.join(REPO_ROOT, "api", "default_docs", "Glass", _GLASS_CONTRACT_FILES[kind])
        try:
            with open(path, encoding="utf-8") as handle:
                return {"ok": True, "kind": kind, "contract": handle.read()}
        except OSError as error:
            return {"ok": False, "error": f"Could not read the {kind} authoring contract: {error}"}
    filename = _CONTRACT_FILES.get(kind)
    if filename is None:
        return {
            "ok": False,
            "error": (f"unknown kind '{kind}'; expected one of: "
                      f"{', '.join((*_CONTRACT_FILES, *_GLASS_CONTRACT_FILES))}"),
        }

    contract_text, error = _read_authoring_doc(filename, f"{kind} authoring contract")
    if error:
        return {"ok": False, "error": error}

    return {"ok": True, "kind": kind,
            "contract": contract_text + _staging_appendix(kind)}


def get_glass_context(date: str, lookahead_days: int = 14, include_pane_schemas: bool = False) -> dict:
    """Public schedule/calendar context only; no Canvas or student reads."""
    from datetime import date as date_type
    from api.glass import panes
    from api.glass.day_context import day_context
    try:
        day = date_type.fromisoformat(date)
    except (TypeError, ValueError):
        return {"ok": False, "error": "date must be YYYY-MM-DD"}
    if isinstance(lookahead_days, bool) or not isinstance(lookahead_days, int) or not 0 <= lookahead_days <= 31:
        return {"ok": False, "error": "lookahead_days must be an integer from 0 to 31"}
    context = day_context(day, lookahead_days=lookahead_days)
    blocks = context["blocks"]
    approved = []
    for item in panes.list_approved()["panes"]:
        entry = {"pane_id": item["pane_id"], "revision": item["revision"], "title": item["title"]}
        if include_pane_schemas: entry["data_schema"] = item["data_schema"]
        approved.append(entry)
    scene = panes.approved_scene(day)
    pending = next((item for item in panes.list_drafts() if item["kind"] == "scene" and item["subject"] == date), None)
    return {"ok": True, "date": date, "day_type": context["day_type"],
            "blocks": blocks, "events": context["events"], "grading_periods": context["grading_periods"],
            "approved_panes": approved,
            "approved_scene": {"approved": bool(scene), "digest": scene["digest"] if scene else None},
            "pending_scene": {"pending": bool(pending), "draft_id": pending["draft_id"] if pending else None,
                              "digest": pending["digest"] if pending else None}}


def save_glass_pane_draft(manifest: dict, pane_html: str, pane_css: str = "", pane_js: str = "", assets: list | None = None, draft_id: str = "") -> dict:
    from api.glass import panes
    return panes.save_pane_draft({"manifest": manifest, "pane_html": pane_html, "pane_css": pane_css, "pane_js": pane_js, "assets": assets or []}, draft_id)


def save_glass_scene_draft(scene: dict, draft_id: str = "") -> dict:
    from api.glass import panes
    return panes.save_scene_draft(scene, draft_id)


def list_glass_drafts() -> dict:
    from api.glass import panes
    return {"ok": True, "drafts": panes.list_drafts()}


def get_product_guide(topic: str = "") -> dict:
    """One CanvasExpert product guide, served verbatim from the same
    ``api/default_docs/AI Authoring/`` source the web UI hands out. No
    course_id, no student data — no course gate, no vault, no safety gate.

    ``topic`` defaults to the whole CanvasAgent briefing (what the app can do,
    the hard lines, the staging loop, privacy, troubleshooting).
    ``writing_timeline`` is the tracked / not-tracked reference.
    ``writing_record`` covers get_writing_history: the per-student
    longitudinal writing record, what it returns, and what it does not have
    yet. Every response lists the available topics so the assistant learns
    what else it can pull without a second guess."""
    requested = str(topic or "").strip().lower() or _DEFAULT_GUIDE_TOPIC
    filename = _GUIDE_FILES.get(requested)
    if filename is None:
        return {
            "ok": False,
            "error": (f"unknown topic '{requested}'; expected one of: "
                      f"{', '.join(_GUIDE_FILES)} (or omit for "
                      f"{_DEFAULT_GUIDE_TOPIC})"),
        }

    guide_text, error = _read_authoring_doc(filename, f"{requested} guide")
    if error:
        return {"ok": False, "error": error}

    return {"ok": True, "topic": requested,
            "topics": list(_GUIDE_FILES), "guide": guide_text}


def list_staged_content(kind: str = "") -> dict:
    """Drafts an assistant has already staged in the per-kind Inbox, so it can
    confirm a drop landed and avoid losing track or duplicating it. Reuses
    ``webui.deps.list_inbox_files`` (the Slice C marker gate) as-is. Pass one
    of quiz/assignment/page/rubric to narrow to that kind, or omit for all
    four. No course_id, no student data — no course gate, no vault, no safety
    gate. Only each draft's label (name) is returned, never its absolute
    path."""
    if kind:
        if kind not in _CONTRACT_FILES:
            return {
                "ok": False,
                "error": (f"unknown kind '{kind}'; expected one of: "
                          f"{', '.join(_CONTRACT_FILES)} (or omit for all)"),
            }
        kinds = [kind]
    else:
        kinds = list(_CONTRACT_FILES)

    rows = [
        {"kind": k, "label": entry["label"]}
        for k in kinds
        for entry in deps.list_inbox_files(k)
    ]
    return {"ok": True, "staged": _tabulate(rows, _STAGED_CONTENT_COLUMNS)}


_MIRROR_UNAVAILABLE_ROSTER_ERROR = (
    "The local CanvasMirror roster for this course is stale or missing. "
    "Canvas Expert withholds it rather than fetching live from Canvas — call "
    "refresh_mirror for this course, then try again."
)
_MIRROR_UNAVAILABLE_SUBMISSIONS_ERROR = (
    "The local CanvasMirror for this course (roster, assignments, or "
    "submissions) is stale or missing. Canvas Expert withholds submissions "
    "rather than fetching live from Canvas — call refresh_mirror for this "
    "course, then try again."
)
_MIRROR_UNAVAILABLE_SNAPSHOT_ERROR = (
    "The local CanvasMirror for this course isn't fresh enough to serve a "
    "whole-course snapshot. Canvas Expert withholds it rather than fetching "
    "live from Canvas — call refresh_mirror for this course, then try again."
)


def get_roster(course_id: str) -> dict:
    """Current roster as a {columns, rows} table of (pseudonym,
    section_names), sorted by pseudonym. Served ONLY from the local
    CanvasMirror — never live Canvas; a stale or missing mirror is refused
    (call refresh_mirror first). Pseudonymized through the identity vault;
    gated by the outbound safety scan before tabulation."""
    err = _course_gate_check(course_id)
    if err:
        return {"ok": False, "error": err}

    vault, vault_err = _open_vault()
    if vault_err:
        return {"ok": False, "error": vault_err}

    mirror_doc = _mirror_roster_doc(course_id)
    if mirror_doc is None:
        return {"ok": False, "error": _MIRROR_UNAVAILABLE_ROSTER_ERROR}

    with _vault_transaction(vault):
        users = mirror_doc["students"]
        roster_service.upsert_roster(vault, users)
        roster = pseudonym.pseudonymize_roster(vault, users, mirror_doc["sections"])
        result = pseudonym.gate(
            {"roster": roster, "source": "mirror",
             "synced_at": mirror_doc["last_success_at"]}, vault)
    if result.get("ok"):
        result["roster"] = _tabulate(result["roster"], _ROSTER_COLUMNS)
    return result


def get_seating_context(course_id: str, section_name: str) -> dict:
    """Pseudonymized mirror+local seating context for one exact section name.

    Current mirrored identity/membership is joined with private local Roster
    context. This deliberately narrow projection carries neither Canvas
    identifiers nor private local reasons/notes, and it refuses rather than
    guessing when mirror section names are absent or ambiguous.
    """
    err = _course_gate_check(course_id)
    if err:
        return {"ok": False, "error": err}
    if not isinstance(section_name, str):
        return {"ok": False, "error": "A section name is required."}

    vault, vault_err = _open_vault()
    if vault_err:
        return {"ok": False, "error": vault_err}
    mirror_doc = _mirror_roster_doc(course_id)
    if mirror_doc is None:
        return {"ok": False, "error": _MIRROR_UNAVAILABLE_ROSTER_ERROR}

    section_ids = [
        str(section_id) for section_id, name in mirror_doc["sections"].items()
        if name == section_name
    ]
    if len(section_ids) != 1:
        return {
            "ok": False,
            "error": "The requested local mirror section is missing or ambiguous; student data is withheld.",
        }
    selected_section_id = section_ids[0]

    with _vault_transaction(vault):
        users = mirror_doc["students"]
        roster_service.upsert_roster(vault, users)
        selected_users = []
        for user in users:
            enrolled_section_ids = {
                str(enrollment.get("course_section_id") or "")
                for enrollment in user.get("enrollments") or []
            }
            if selected_section_id in enrolled_section_ids and user.get("id") is not None:
                selected_users.append(user)

        settings = config.get_roster_student_settings(course_id)
        score_matrix = roster_context._normalize_score_matrix(
            config.get_roster_score_matrix(course_id)
        )
        relationships = roster_context.normalize_relationships(
            config.get_roster_relationships(course_id)
        )
        replacement_map = feedback_scrub.build_replacement_map(
            vault.entries(), set(config.active_protected_names())
        )
        columns = score_matrix["columns"]
        values_by_student = score_matrix["values_by_section"].get(selected_section_id, {})
        student_payload: list[dict] = []
        pseudonyms_by_id: dict[str, str] = {}
        selected_ids: set[str] = set()
        for user in selected_users:
            student_id = str(user["id"])
            pseudo = vault.get_or_assign(user["id"])
            pseudonyms_by_id[student_id] = pseudo
            selected_ids.add(student_id)
            local_settings = settings.get(student_id, {}) if isinstance(settings, dict) else {}
            seating = roster_context.normalize_seating_context(
                local_settings.get("seating_context") if isinstance(local_settings, dict) else None
            )
            raw_scores = values_by_student.get(student_id, {})
            scores = [
                {
                    "label": feedback_scrub.scrub_text(column["label"], replacement_map),
                    "value": raw_scores[column["id"]],
                }
                for column in columns
                if column["id"] in raw_scores
            ]
            student_payload.append({
                "pseudonym": pseudo,
                "supports": {
                    "front_row": seating["front_row"],
                    "near_teacher": seating["near_teacher"],
                },
                "scores": scores,
                "ai_context_note": feedback_scrub.scrub_text(
                    seating["ai_context_note"], replacement_map
                ),
            })

        relationship_payload = []
        for item in relationships["by_section"].get(selected_section_id, []):
            first, second = item["student_a"], item["student_b"]
            if first not in selected_ids or second not in selected_ids:
                continue
            relationship_payload.append({
                "type": item["type"],
                "students": sorted((pseudonyms_by_id[first], pseudonyms_by_id[second])),
            })

        student_payload.sort(key=lambda item: item["pseudonym"])
        relationship_payload.sort(
            key=lambda item: (item["type"], item["students"][0], item["students"][1])
        )
        return pseudonym.gate({
            "students": student_payload,
            "relationships": relationship_payload,
            "source": "mirror+local",
            "synced_at": mirror_doc["last_success_at"],
        }, vault)


def get_submissions(course_id: str, assignment_id: str,
                    include_text: bool = True, pseudonyms: str = "",
                    max_text_chars: int = _DEFAULT_MAX_TEXT_CHARS) -> dict:
    """One assignment's submissions, pseudonymized and scrubbed, as
    ``{assignment: {...}, submissions: {columns, rows}}``. Served ONLY from
    the local CanvasMirror — never live Canvas; a stale or missing mirror is
    refused (call refresh_mirror first). ``pseudonyms`` (comma-separated)
    narrows to specific students; ``include_text=False`` drops the text
    column; text is trimmed to ``max_text_chars`` (0 = full). Attachments are
    never included. Gated by the outbound safety scan."""
    err = _course_gate_check(course_id)
    if err:
        return {"ok": False, "error": err}

    vault, vault_err = _open_vault()
    if vault_err:
        return {"ok": False, "error": vault_err}

    bundle, bundle_err = _mirror_submission_bundle(course_id, assignment_id)
    if bundle_err:
        return {"ok": False, "error": bundle_err}
    if bundle is None:
        return {"ok": False, "error": _MIRROR_UNAVAILABLE_SUBMISSIONS_ERROR}

    # Sync the full roster first so the scrub map covers every enrolled
    # student, not just the ones who submitted this assignment.
    with _vault_transaction(vault):
        roster_service.upsert_roster(vault, bundle["roster"])
        assignment, subs = bundle["assignment"], bundle["rows"]

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
            "source": "mirror",
            "synced_at": bundle["synced_at"],
        }
        result = pseudonym.gate(payload, vault)
    if result.get("ok"):
        columns = (_SUBMISSION_COLUMNS if include_text
                   else tuple(c for c in _SUBMISSION_COLUMNS if c != "text"))
        result["submissions"] = _tabulate(result["submissions"], columns)
    return result


# A student's writing history has no session lookback of its own to borrow, and
# the substrate landed 2026-07-27 -- so any student's real history today is far
# shorter than this. Two years keeps the default call cheap and bounded rather
# than scanning from date.min, while being generous enough that "since"/"until"
# only need to be passed when someone actually wants to narrow the window.
_DEFAULT_HISTORY_LOOKBACK_DAYS = 730


def get_writing_history(pseudonym: str, since: str = "", until: str = "",
                        include_text: bool = False,
                        max_text_chars: int = _DEFAULT_MAX_TEXT_CHARS) -> dict:
    """One student's Writing Record evidence across time, pseudonym-first:
    dated submissions, assignment context, word counts, segment attribution,
    and structural flags. Writing Record does not score, coach, or judge work.
    Read from the private per-student store
    (``api/dailywriting``), never from a course or the CanvasMirror -- there
    is no ``course_id`` here because the store has no course concept and
    nothing to refresh, but the identity vault and the outbound safety gate
    still apply: this is the first tool to carry student data with no
    ``course_id`` gate.

    No judgment is computed here; the assistant and teacher may evaluate the
    evidence later if they choose.
    ``since``/``until`` are ``YYYY-MM-DD`` dates (both default to a two-year
    lookback from today). ``include_text=False`` (the default) omits every
    span quoted from student writing; ``include_text=True`` includes them
    trimmed to ``max_text_chars`` (0 = full), trimmed BEFORE the gate scans
    them. The assignment prompt is teacher-authored, not student data, and is
    always included."""
    vault, vault_err = _open_vault()
    if vault_err:
        return {"ok": False, "error": vault_err}

    try:
        until_date = date.fromisoformat(until) if until else date.today()
        since_date = (date.fromisoformat(since) if since else
                      until_date - timedelta(days=_DEFAULT_HISTORY_LOOKBACK_DAYS))
    except ValueError as error:
        return {"ok": False,
                "error": f"since/until must be YYYY-MM-DD dates: {error}"}
    if since_date > until_date:
        return {"ok": False, "error": "since is after until"}

    try:
        repository = _dailywriting_repository_factory()
    except DailyWritingStoreError as error:
        return {"ok": False, "error": str(error)}

    try:
        submissions = repository.submissions_in_window(
            pseudonym, since_date, until_date)
        reps = {}
        for submission in submissions:
            if submission.rep_id not in reps:
                reps[submission.rep_id] = repository.read_rep(submission.rep_id)
    except IdentityError:
        return {
            "ok": False,
            "error": (f"'{pseudonym}' is not a known pseudonym in the "
                      "identity vault; sync the roster for this student's "
                      "section in the CanvasExpert web UI, then retry."),
        }

    payload = dailywriting_projection.build_history_payload(
        pseudonym_id=pseudonym,
        since=since_date,
        until=until_date,
        submissions=submissions,
        reps=reps,
        include_text=include_text,
        max_text_chars=max_text_chars,
    )
    return _pseudonym_gate(payload, vault)


def get_gradebook_snapshot(course_id: str) -> dict:
    """Whole-course grading snapshot, pseudonymized: per-assignment stats
    (``title`` instead of ``name``, no ``html_url``) and per-student stats
    (``pseudonym`` instead of a name), each as a {columns, rows} table.
    Served ONLY from the local CanvasMirror — never live Canvas; a stale or
    missing mirror is refused (call refresh_mirror first). Gated by the
    outbound safety scan before tabulation."""
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


_REFRESH_TIMEOUT_SECONDS = 25.0

# refresh_mirror drives a submissions delta (course.refresh) AND a roster
# pass, so a roster that has aged past the serve window is recoverable on
# demand. Without the explicit roster scope the manual refresh runs a delta
# only, which never rewrites the roster file — get_roster/get_seating_context
# would then refuse indefinitely (the assistant loops: refresh says "synced",
# the roster stays stale) while the gradebook served fine off deltas. The
# background heartbeat closes the same gap from the other side; see
# mirror_service.due_passes.
_REFRESH_SCOPES = ["course.refresh", "roster"]


def refresh_mirror(course_id: str) -> dict:
    """Ask Canvas Expert to sync this course's local CanvasMirror from Canvas
    (a submissions delta plus a roster refresh), then report freshness — the
    response is a sync STATUS, never Canvas data. Call this after
    get_roster/get_submissions/get_gradebook_snapshot refuses as stale or
    unavailable, then re-call that same tool; this tool never returns course,
    roster, or submission data itself, so it needs no identity vault and no
    outbound safety scan."""
    err = _course_gate_check(course_id)
    if err:
        return {"ok": False, "error": err}

    try:
        plan_id = _enqueue_sync(course_id, _REFRESH_SCOPES)
    except ValueError as error:
        return {"ok": False, "error": str(error)}
    except Exception as error:
        return {"ok": False, "error": f"Could not start a sync: {error}"}

    plan = _wait_for_plan(plan_id, timeout_seconds=_REFRESH_TIMEOUT_SECONDS)
    state = plan.get("state", "failed")
    if state == "succeeded":
        return {"ok": True, "status": "synced",
                "message": "Mirror refreshed. Re-read the data now."}
    if state in ("queued", "running"):
        return {"ok": True, "status": "syncing",
                "message": "Still syncing — wait a few seconds, then try again."}
    return {"ok": False, "status": "failed",
            "error": "Sync failed. Try again, or use Sync now in the CanvasExpert web UI."}
