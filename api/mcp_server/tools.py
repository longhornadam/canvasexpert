"""Plain, testable implementations of the MCP tools.

The authoritative tool count and shape live in ``contract.TOOL_SCHEMA_VERSION``
and its snapshot file, never in prose here.

Every function returns a ``{"ok": ...}`` dict and never raises — that keeps
errors structured for the LLM and matches the rest of the app's route style.
Fetchers and the vault factory are bound to module-level names so tests can
monkeypatch them without touching the real Canvas API or identity vault
(same pattern as ``api/tests/test_gradebook_routes.py``).

Every ``course_id`` tool gates on ``config.active_courses()`` — the same
Current-course scope the web UI uses. ``list_courses``,
``get_authoring_contract``, ``get_product_guide``, ``list_staged_content``,
``get_bell_schedule``, ``get_day_schedule``, ``get_teacher_schedule``,
``save_teacher_schedule``,
``get_school_calendar``, ``preview_school_calendar_replacement``,
``apply_school_calendar_replacement``,
``preview_school_calendar_change``, ``apply_school_calendar_change``,
the only tools with no ``course_id`` and no student data, so they skip both the
course gate and the outbound safety gate. ``get_writing_history`` breaks that
pairing on purpose: it has no ``course_id`` either (the daily-writing store has
no course concept), but it is student data, so it still runs the identity vault
and the outbound safety gate.

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
import hashlib
import json
from contextlib import contextmanager
from datetime import date, timedelta

from api import course_scope, feedback_scrub, gradebook_queries, gradebook_snapshot, learning_objectives, panel_themes, roster_context, roster_service
from api.mirror import queries as mirror_queries
from api.mirror import read_service
from api.mirror import store as mirror_store
from api.webui import config, mirror_service, workspace, schedule_setup, school_calendar
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
_PAGE_COLUMNS = ("id", "title", "body_text", "published", "front_page", "updated_at")
_STAGED_CONTENT_COLUMNS = ("kind", "label")
_SCORING_SESSION_COLUMNS = ("session_id", "assignment_name", "course_id", "created",
                            "mode_label", "total", "scored", "approved")
_PACKET_ITEM_COLUMNS = ("item_id", "prompt", "possible")
_PACKET_STUDENT_COLUMNS = ("pseudonym", "item_id", "text")


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


# ---------------------------------------------------------------------------
# Pseudonym-first local Roster settings tools (schema v21)
# ---------------------------------------------------------------------------

_MCP_ROSTER_PATCH_KEYS = {
    "pseudonym", "regenerate_pseudonym", "extra_time", "monitored",
    "canvas_group", "seating_context", "classroom_profile", "add_nicknames",
}
_MCP_ROSTER_CLEAR_KEYS = {"extra_time", "monitored", "seating_context", "classroom_profile"}
# The seating fields an MCP caller may see and set. private_note is absent on
# purpose: it is teacher-only, so it is neither returned nor writable here.
_MCP_SEATING_KEYS = {"front_row", "near_teacher", "ai_context_note"}


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _roster_group_for_user(course_id: str, user_id: str) -> dict | None:
    document = mirror_store.read_groups(course_id) or {}
    scheme = config.get_roster_group_scheme(course_id)
    selected = str(scheme.get("selected_group_category_id") or "")
    for category in document.get("categories") or document.get("groups") or []:
        category_id = str(category.get("category_id") or category.get("id") or "")
        if selected and category_id != selected:
            continue
        for group in category.get("groups") or []:
            members = group.get("student_ids") or []
            if str(user_id) in {str(member) for member in members}:
                return {"category_id": category_id, "group_id": str(group.get("id") or ""),
                        "group_name": group.get("name") or ""}
            for membership in group.get("memberships") or []:
                if str(membership.get("user_id") or "") == str(user_id):
                    return {"category_id": category_id, "group_id": str(group.get("id") or ""),
                            "group_name": group.get("name") or ""}
    return None


def _roster_full_record(course_id: str, user_id: str, vault) -> dict:
    vault_entry = next((entry for entry in vault.entries()
                        if str(entry.get("canvas_id")) == str(user_id)), {})
    local = config.get_roster_student_settings(course_id) or {}
    local_entry = local.get(str(user_id), {}) if isinstance(local, dict) else {}
    extra = next((entry for entry in config.get_extra_time(course_id) or []
                  if str(entry.get("id")) == str(user_id)), None)
    monitored = (config.get_monitored_students() or {}).get(str(user_id))
    return {
        "vault": vault_entry,
        "local": local_entry if isinstance(local_entry, dict) else {},
        "extra_time": extra,
        "monitored": monitored,
        "canvas_group": _roster_group_for_user(course_id, user_id),
    }


def _roster_safe_projection(course_id: str, user_id: str, vault) -> dict:
    record = _roster_full_record(course_id, user_id, vault)
    local = record["local"]
    extra = record["extra_time"] or {}
    monitored = record["monitored"] or {}
    group = record["canvas_group"]
    seating = roster_context.normalize_seating_context(local.get("seating_context"))
    profile = local.get("classroom_profile", config.empty_classroom_profile())
    try:
        profile = config.validate_classroom_profile(profile)
    except ValueError:
        profile = config.empty_classroom_profile()
    # private_note is teacher-only and never leaves the machine, matching
    # get_seating_context, which emits front_row/near_teacher plus a scrubbed
    # ai_context_note and no private note at all. ai_context_note is free text
    # a teacher typed, so it is scrubbed here rather than trusted: pseudonym.gate
    # only soft-flags a roster name in free text, and a soft flag does not block.
    replacement_map = feedback_scrub.build_replacement_map(
        vault.entries(), set(config.active_protected_names())
    )
    return {
        "pseudonym": record["vault"].get("pseudonym", ""),
        "extra_time": {"enabled": bool(extra), "days": extra.get("days", 0) if extra else 0},
        "monitored": {"enabled": bool(monitored)},
        "canvas_group": group,
        "seating_context": {
            "front_row": seating["front_row"], "near_teacher": seating["near_teacher"],
            "ai_context_note": feedback_scrub.scrub_text(
                seating["ai_context_note"], replacement_map),
        },
        "classroom_profile": profile,
    }


def _open_roster_student(course_id: str, requested: str):
    vault, vault_err = _open_vault()
    if vault_err:
        return None, vault_err
    mirror_doc = _mirror_roster_doc(course_id)
    if mirror_doc is None:
        return None, _MIRROR_UNAVAILABLE_ROSTER_ERROR
    with _vault_transaction(vault):
        roster_service.upsert_roster(vault, mirror_doc["students"])
        user_id = pseudonym.resolve_pseudonym(vault, mirror_doc["students"], requested)
        if not user_id:
            return None, "No current local roster student matches that pseudonym."
        return {"vault": vault, "students": mirror_doc["students"], "user_id": user_id}, None


def _gate_roster_result(payload: dict, vault) -> dict:
    return pseudonym.gate(payload, vault)


def _validate_mcp_roster_patch(patch: object) -> tuple[dict | None, str | None]:
    if not isinstance(patch, dict):
        return None, "patch must be an object."
    if "nicknames" in patch:
        return None, "nicknames is not available through MCP; use add_nicknames."
    unknown = set(patch) - _MCP_ROSTER_PATCH_KEYS
    if unknown:
        return None, f"Unknown patch keys: {sorted(unknown)}"
    if "add_nicknames" in patch and (
        not isinstance(patch["add_nicknames"], list)
        or any(not isinstance(value, str) for value in patch["add_nicknames"])
    ):
        return None, "add_nicknames must be a list of strings."
    if "seating_context" in patch:
        seating = patch["seating_context"]
        if not isinstance(seating, dict):
            return None, "seating_context must be an object."
        if "private_note" in seating:
            return None, ("seating_context.private_note is not available through MCP; "
                          "edit it in the Roster page.")
        unknown = set(seating) - _MCP_SEATING_KEYS
        if unknown:
            return None, f"Unknown seating_context keys: {sorted(unknown)}"
    return patch, None


def _merge_stored_private_note(course_id: str, user_id: str, patch: dict) -> dict:
    """Fill the fields an MCP caller cannot see back in before storage.

    validate_seating_context requires the exact full field set, and MCP can
    neither read nor write private_note. Without this, every seating write from
    an assistant would have to send a blank private note and would silently
    erase whatever the teacher typed there.
    """
    if "seating_context" not in patch:
        return patch
    local = config.get_roster_student_settings(course_id) or {}
    entry = local.get(str(user_id), {}) if isinstance(local, dict) else {}
    stored = roster_context.normalize_seating_context(
        entry.get("seating_context") if isinstance(entry, dict) else None)
    merged = dict(patch)
    supplied = dict(patch["seating_context"])
    merged["seating_context"] = {
        "front_row": supplied.get("front_row", stored["front_row"]),
        "near_teacher": supplied.get("near_teacher", stored["near_teacher"]),
        "ai_context_note": supplied.get("ai_context_note", stored["ai_context_note"]),
        "private_note": stored["private_note"],
    }
    return merged


def get_roster_student_settings(course_id: str, pseudonym: str) -> dict:
    err = _course_gate_check(course_id)
    if err:
        return {"ok": False, "error": err}
    target, error = _open_roster_student(course_id, pseudonym)
    if error:
        return {"ok": False, "error": error}
    vault, user_id = target["vault"], target["user_id"]
    result = _gate_roster_result({
        "pseudonym": vault.get_or_assign(user_id),
        "settings": _roster_safe_projection(course_id, user_id, vault),
        "settings_digest": _canonical_digest(_roster_full_record(course_id, user_id, vault)),
    }, vault)
    return result


def preview_roster_student_change(course_id: str, pseudonym: str, patch: dict) -> dict:
    err = _course_gate_check(course_id)
    if err:
        return {"ok": False, "error": err}
    patch, error = _validate_mcp_roster_patch(patch)
    if error:
        return {"ok": False, "error": error}
    target, error = _open_roster_student(course_id, pseudonym)
    if error:
        return {"ok": False, "error": error}
    vault, user_id = target["vault"], target["user_id"]
    before = _roster_safe_projection(course_id, user_id, vault)
    after = dict(before)
    for key, value in patch.items():
        if key == "add_nicknames":
            after[key] = list(value)
        elif key == "regenerate_pseudonym":
            after[key] = bool(value)
        else:
            after[key] = value
    preview = {"pseudonym": before["pseudonym"], "patch": patch,
               "before": {key: before.get(key) for key in patch},
               "after": {key: after.get(key) for key in patch},
               "settings_digest": _canonical_digest(_roster_full_record(course_id, user_id, vault))}
    return _gate_roster_result({
        "pseudonym": before["pseudonym"],
        "settings_digest": preview["settings_digest"],
        "preview": preview,
        "preview_digest": _canonical_digest(preview),
    }, vault)


def _apply_roster_update(course_id: str, vault, user_id: str, patch: dict) -> dict:
    from api.webui import roster_mcp
    return roster_mcp.update_student(
        course_id, user_id, _merge_stored_private_note(course_id, user_id, patch), vault)


def apply_roster_student_change(course_id: str, preview: dict,
                                preview_digest: str, expected_settings_digest: str) -> dict:
    err = _course_gate_check(course_id)
    if err:
        return {"ok": False, "error": err}
    if not isinstance(preview, dict) or _canonical_digest(preview) != preview_digest:
        return {"ok": False, "error": "Preview digest mismatch; nothing was written."}
    if preview.get("settings_digest") != expected_settings_digest:
        return {"ok": False, "error": "Expected settings digest does not match the preview; nothing was written."}
    requested = preview.get("pseudonym")
    patch, error = _validate_mcp_roster_patch(preview.get("patch"))
    if error:
        return {"ok": False, "error": error}
    target, error = _open_roster_student(course_id, requested)
    if error:
        return {"ok": False, "error": error}
    vault, user_id = target["vault"], target["user_id"]
    current_digest = _canonical_digest(_roster_full_record(course_id, user_id, vault))
    if current_digest != expected_settings_digest:
        return {"ok": False, "error": "Settings changed since preview; nothing was written."}
    result = _apply_roster_update(course_id, vault, user_id, patch)
    if not result.get("ok"):
        return result
    fresh = _roster_full_record(course_id, user_id, vault)
    return _gate_roster_result({"pseudonym": vault.get_or_assign(user_id),
                                "settings_digest": _canonical_digest(fresh)}, vault)


def clear_roster_student_field(course_id: str, pseudonym: str, field: str,
                               expected_settings_digest: str) -> dict:
    err = _course_gate_check(course_id)
    if err:
        return {"ok": False, "error": err}
    if field in {"nicknames", "add_nicknames"}:
        return {"ok": False, "error": f"{field} cannot be cleared through MCP."}
    if field not in _MCP_ROSTER_CLEAR_KEYS:
        return {"ok": False, "error": "That roster field has no supported direct clear operation."}
    target, error = _open_roster_student(course_id, pseudonym)
    if error:
        return {"ok": False, "error": error}
    vault, user_id = target["vault"], target["user_id"]
    if _canonical_digest(_roster_full_record(course_id, user_id, vault)) != expected_settings_digest:
        return {"ok": False, "error": "Settings changed since read; nothing was written."}
    patch = {
        "extra_time": {"enabled": False} if field == "extra_time" else None,
        "monitored": {"enabled": False} if field == "monitored" else None,
        "seating_context": {"front_row": "none", "near_teacher": "none",
                             "private_note": "", "ai_context_note": ""} if field == "seating_context" else None,
        "classroom_profile": config.empty_classroom_profile() if field == "classroom_profile" else None,
    }
    result = _apply_roster_update(course_id, vault, user_id, {field: patch[field]})
    if not result.get("ok"):
        return result
    return _gate_roster_result({"pseudonym": vault.get_or_assign(user_id),
                                "settings_digest": _canonical_digest(_roster_full_record(course_id, user_id, vault))}, vault)


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
    Canvas fallback) for any saved course (Current or Previous). No student
    data — no vault, no safety gate. Returns
    a {columns, rows} table of (section_id, section_name). Call this before
    get_seating_context to discover valid section_name values."""
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
    Canvas fallback — refresh the catalog from the web UI first) for any
    saved course (Current or Previous). No student data — no safety gate.
    Descriptions are trimmed to a preview unless ``full_descriptions`` is set;
    assignments go out as a {columns, rows} table."""

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
    Canvas fallback — refresh the catalog from the web UI first) for any
    saved course (Current or Previous). No student data — no vault, no safety
    gate. Staleness is labeled (source, synced_at, state), never refused,
    since modules are structural, not student data. Modules go out as a
    {columns, rows} table; include_items nests each module's items as their
    own {columns, rows} table. ``published`` is included only when the catalog
    record actually carries it."""

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


def get_course_pages(course_id: str, full_text: bool = False) -> dict:
    """Published page projection from the local v3 Catalog for the Current course.

    The refresh route is the only Canvas acquisition path. This read never
    refreshes, falls back to Canvas, or exposes the workspace path.
    """
    gate_error = _course_gate_check(course_id)
    if gate_error:
        return {"ok": False, "error": gate_error}
    read_result = read_catalog(course_id)
    scope = read_service.catalog_pages(
        course_id, catalog_reader=lambda _course_id: read_result,
    )
    if scope["source"] == "none":
        return {
            "ok": False,
            "error": ("No local course catalog found for this course. Refresh "
                      "the catalog from the CanvasExpert web UI, then try again."),
        }
    body_chars = 0 if full_text else _DESCRIPTION_PREVIEW_CHARS
    pages = [{
        "id": page.get("id"),
        "title": page.get("title", ""),
        "body_text": _truncate_text(page.get("body_text", ""), body_chars),
        "published": page.get("published") is True,
        "front_page": page.get("front_page") is True,
        "updated_at": page.get("updated_at", ""),
    } for page in scope["records"] if page.get("published") is True]
    return {
        "ok": True,
        "course_id": str((read_result.get("catalog") or {}).get("course_id") or course_id),
        "course_name": str((read_result.get("catalog") or {}).get("course_name") or ""),
        "pages": _tabulate(pages, _PAGE_COLUMNS),
        "source": scope["source"],
        "synced_at": scope["last_success_at"],
        "state": scope["state"],
    }


def preview_learning_objective(course_id: str, objective: str,
                               effective_start: str, effective_end: str,
                               source_refs: list, replaces: str = None) -> dict:
    """Build the exact reviewed objective preview; never writes or calls Canvas."""
    gate_error = _course_gate_check(course_id)
    if gate_error:
        return {"ok": False, "error": gate_error}
    try:
        read_result = read_catalog(course_id)
        catalog = read_result.get("catalog") if isinstance(read_result, dict) else None
        if not isinstance(catalog, dict):
            raise ValueError("No local course catalog found for this course. Refresh the catalog first.")
        document = learning_objectives.read_document()
        result = learning_objectives.build_preview(
            course_id=str(course_id), catalog=catalog, document=document,
            objective=objective, effective_start=effective_start,
            effective_end=effective_end, source_refs=source_refs, replaces=replaces,
        )
        return {"ok": True, **result}
    except (OSError, TypeError, ValueError) as error:
        return {"ok": False, "error": str(error)}


def apply_learning_objective(course_id: str, preview: dict,
                             preview_digest: str, expected_revision: int) -> dict:
    """Apply only the exact current preview after all concurrency checks."""
    gate_error = _course_gate_check(course_id)
    if gate_error:
        return {"ok": False, "error": gate_error}
    try:
        read_result = read_catalog(course_id)
        catalog = read_result.get("catalog") if isinstance(read_result, dict) else None
        if not isinstance(catalog, dict):
            raise ValueError("No local course catalog found for this course. Refresh the catalog first.")
        document = learning_objectives.read_document()
        written = learning_objectives.apply_preview(
            course_id=str(course_id), preview=preview,
            preview_digest_value=preview_digest,
            expected_revision=expected_revision, catalog=catalog,
            document=document,
        )
        return {"ok": True, "revision": written["revision"],
                "course_id": str(course_id)}
    except (OSError, TypeError, ValueError) as error:
        return {"ok": False, "error": str(error)}


def list_learning_objectives(course_id: str) -> dict:
    """List the reviewed objectives for a Current course without student data."""
    gate_error = _course_gate_check(course_id)
    if gate_error:
        return {"ok": False, "error": gate_error}
    try:
        document = learning_objectives.read_document()
        rows = []
        for entry in document["objectives"].get(str(course_id), []):
            rows.append([
                entry["id"], entry["objective"], entry["effective_start"],
                entry["effective_end"], [ref["title"] for ref in entry["source_refs"]],
                entry["authored_at"],
            ])
        return {"ok": True, "course_id": str(course_id),
                "revision": document["revision"],
                "objectives": {"columns": [
                    "id", "objective", "effective_start", "effective_end",
                    "source_titles", "authored_at",
                ], "rows": rows}}
    except (OSError, TypeError, ValueError) as error:
        return {"ok": False, "error": str(error)}


def delete_learning_objective(course_id: str, entry_id: str, expected_revision: int) -> dict:
    """Delete one reviewed objective with an explicit revision guard."""
    gate_error = _course_gate_check(course_id)
    if gate_error:
        return {"ok": False, "error": gate_error}
    try:
        written = learning_objectives.delete_entry(
            course_id=str(course_id), entry_id=entry_id,
            expected_revision=expected_revision,
        )
        return {"ok": True, "course_id": str(course_id), "revision": written["revision"]}
    except (OSError, TypeError, ValueError) as error:
        return {"ok": False, "error": str(error)}


# ── Panel themes ─────────────────────────────────────────────────────────
# A theme is a skin for a Panel: a palette, a face, and one decorative layer,
# kept as a JSON file in the teacher's synced Library. No course_id, no student
# data, so no course gate and no outbound safety gate.
#
# The assistant's job here is taste, not safety. It proposes colours; the
# generator derives the twenty variables a Panel actually consumes, corrects
# any text colour that would not clear 4.5:1 on a projector, and refuses
# anything outside the closed font and ornament sets. That is why these tools
# can hand a file-writing surface to an LLM without a review queue.

def get_theme_contract() -> dict:
    """The Panel theme format: what you may set, and what is derived for you."""
    try:
        builtins = sorted(panel_themes.BUILTIN_KEYS)
        return {
            "ok": True,
            "version": panel_themes.VERSION,
            "where": "Library/Panels/Themes/<key>.json in the teacher's synced workspace",
            "you_set": {
                "key": ("1 to 32 characters, lowercase letters, digits, inner "
                        "hyphens. Must not be a built-in key."),
                "label": f"What the teacher sees in the Theme list, {panel_themes.MAX_LABEL_LENGTH} characters or fewer",
                "font": sorted(panel_themes.FONTS),
                "ornament": list(panel_themes.ORNAMENTS),
                "colors": {
                    "bg": "required, hex, the page behind everything",
                    "ink": "required, hex, body text",
                    "accent": "required, hex, title, footer mark, row bars",
                    "highlight": ("optional, hex, the emphasised row (today, "
                                  "overdue). Defaults to accent, so passing a "
                                  "second colour is what makes today stand out."),
                },
                "art": {
                    "file": ("a filename only, from the art folder "
                             "Library/Panels/Themes/art/. Call list_theme_art "
                             "to see what is there; do not invent a name."),
                    "place": list(panel_themes.ART_PLACES),
                    "size": (f"vmin, clamped {panel_themes.ART_MIN_SIZE} to "
                             f"{panel_themes.ART_MAX_SIZE}. Ignored for cover."),
                    "opacity": (f"clamped {panel_themes.ART_MIN_OPACITY} to "
                                f"{panel_themes.ART_MAX_OPACITY}. Default "
                                f"{panel_themes.ART_DEFAULT_OPACITY}."),
                    "recolor": list(panel_themes.ART_RECOLORS),
                },
            },
            "derived_for_you": [
                "--muted", "--rule", "--row", "--row-alt", "--pill-bg",
                "--pill-ink", "--today-bg", "--today-accent", "--today-ink",
                "--when-ink", "--warn-ink", "--title", "--ornament",
            ],
            "rules": [
                f"Every text-on-background pair is measured and corrected to at least {panel_themes.CONTRAST_FLOOR}:1. "
                "Preview reports anything it moved, so pick colours that already have contrast if you want them kept.",
                "Hex colours only. No alpha: rows stay opaque so text lands on flat colour.",
                "Fonts and ornaments are closed sets. Nothing here may reach the network.",
                "A theme cannot change layout or row counts. It is a palette, a face, and one decorative layer.",
                "Art: you place a teacher's file, you do not draw it. Accepted files are "
                + ", ".join(panel_themes.ART_EXTENSIONS)
                + ". A missing or unreadable file degrades to the gradient ornament and is named in the console.",
            ],
            "builtin_keys": builtins,
            "steps": [
                "preview_panel_theme with the key, label, font, ornament, colours, and art.",
                "Read back preview.contrast and preview.adjustments, and tell the teacher what was corrected.",
                "apply_panel_theme with the preview and its digest.",
                "The theme appears under Yours in the Panels console Theme list, and at ?theme=<key>.",
            ],
            "example": {
                "key": "bobcats", "label": "Bobcats", "font": "sans",
                "ornament": "grid",
                "colors": {"bg": "#f8fafc", "ink": "#101c30",
                           "accent": "#123a70", "highlight": "#c8102e"},
            },
        }
    except (OSError, TypeError, ValueError) as error:
        return {"ok": False, "error": str(error)}


def list_theme_art() -> dict:
    """The art files present, their kind, dimensions or viewBox, and any
    diagnostic. The assistant references filenames that exist instead of
    inventing them."""
    try:
        return {"ok": True, **panel_themes.list_theme_art()}
    except (OSError, TypeError, ValueError) as error:
        return {"ok": False, "error": str(error)}


def list_panel_themes() -> dict:
    """Built-in themes, the teacher's own themes, and any file that failed."""
    try:
        loaded = panel_themes.load_custom_themes()
        rows = [[key, label, "built-in", ""]
                for key, label in panel_themes.BUILTIN_THEMES]
        rows += [[theme["key"], theme["label"], "yours", theme["authored_at"]]
                 for theme in loaded["themes"]]
        return {
            "ok": True,
            "themes": {"columns": ["key", "label", "origin", "authored_at"],
                       "rows": rows},
            "problems": loaded["problems"],
            "custom_count": len(loaded["themes"]),
        }
    except (OSError, TypeError, ValueError) as error:
        return {"ok": False, "error": str(error)}


def preview_panel_theme(key: str, label: str, colors: dict,
                        font: str = panel_themes.DEFAULT_FONT,
                        ornament: str = panel_themes.DEFAULT_ORNAMENT,
                        art: list | None = None) -> dict:
    """Build the exact theme apply would write, with its measured contrast."""
    try:
        preview = panel_themes.build_preview(
            key=key, label=label, colors=colors, font=font, ornament=ornament,
            art=art,
        )
        # Diagnose, never refuse: a background that cannot hold the floor
        # still applies unchanged, same as an unusable art file still renders.
        # This just gives the assistant a plain sentence to pass on.
        if not preview.get("floor_reachable", True):
            notes = preview.setdefault("notes", [])
            notes.append(
                "This background cannot hold text at the "
                f"{panel_themes.CONTRAST_FLOOR}:1 readability floor, it tops "
                f"out at {preview['floor_ceiling']}:1. Panel text is large so "
                "it still reads, but a lighter or darker background reads "
                "better from the back of the room.")
        return {"ok": True, **preview}
    except (OSError, TypeError, ValueError) as error:
        return {"ok": False, "error": str(error)}


def apply_panel_theme(preview: dict, preview_digest: str) -> dict:
    """Write exactly the previewed theme into the teacher's Library."""
    try:
        written = panel_themes.apply_preview(
            preview=preview, preview_digest_value=preview_digest,
        )
        theme = written["theme"]
        return {"ok": True, "key": theme["key"], "label": theme["label"],
                "replaced": written["replaced"],
                "url_hint": f"?theme={theme['key']}"}
    except (OSError, TypeError, ValueError) as error:
        return {"ok": False, "error": str(error)}


def delete_panel_theme(key: str) -> dict:
    """Delete one of the teacher's own themes. Built-ins are not reachable."""
    try:
        if str(key or "").strip().lower() in panel_themes.BUILTIN_KEYS:
            return {"ok": False, "error":
                    f"{key!r} is a built-in theme and cannot be deleted."}
        return {"ok": True, **panel_themes.delete_theme(key)}
    except (OSError, TypeError, ValueError) as error:
        return {"ok": False, "error": str(error)}


_CONTRACT_FILES = {
    "quiz": "Author a Quiz (QuizForge).txt",
    "assignment": "Author an Assignment (AssignmentForge).txt",
    "page": "Author a Page (PageForge).txt",
    "rubric": "Author a Rubric (RubricForge).txt",
    "schedule": "Author a Class Schedule.txt",
    "learning_objective": "Author a Learning Objective.txt",
}
_DIRECT_WRITE_CONTRACT_KINDS = frozenset({"schedule", "learning_objective"})
_STAGED_CONTRACT_KINDS = ("quiz", "assignment", "page", "rubric")

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
    """Return one canonical Forge authoring contract.

    Contracts come from ``api/default_docs/AI Authoring/``. Most receive
    the Forge-only staging appendix; schedule is the direct-write exception
    with no review queue. No course_id, student data, vault,
    or safety gate applies.
    """
    filename = _CONTRACT_FILES.get(kind)
    if filename is None:
        return {
            "ok": False,
            "error": (f"unknown kind '{kind}'; expected one of: "
                      f"{', '.join(_CONTRACT_FILES)}"),
        }

    contract_text, error = _read_authoring_doc(filename, f"{kind} authoring contract")
    if error:
        return {"ok": False, "error": error}

    # Schedule has no staging/review queue. It writes directly to the
    # teacher's local workspace.
    if kind in _DIRECT_WRITE_CONTRACT_KINDS:
        return {"ok": True, "kind": kind, "contract": contract_text}

    return {"ok": True, "kind": kind,
            "contract": contract_text + _staging_appendix(kind)}


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
        if kind not in _STAGED_CONTRACT_KINDS:
            return {
                "ok": False,
                "error": (f"unknown kind '{kind}'; expected one of: "
                      f"{', '.join(_STAGED_CONTRACT_KINDS)} (or omit for all)"),
            }
        kinds = [kind]
    else:
        kinds = list(_STAGED_CONTRACT_KINDS)

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
    outbound safety scan. It accepts any saved course (Current or Previous)."""

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


def get_bell_schedule(schedule_id: str = "") -> dict:
    """Read bell schedule(s) from workspace Calendars folder.

    No course gate, no student data — no safety gate.
    schedule_id: empty string ("") returns all variants as {schedule_id: meetings},
                 non-empty returns just that one or error if not found.
    """
    bell_schedules, problems = deps.load_bell_schedules()

    if schedule_id == "":
        return {
            "ok": True,
            "schedules": bell_schedules,
            "problems": problems,
        }

    if schedule_id not in bell_schedules:
        return {
            "ok": False,
            "error": f"schedule '{schedule_id}' not found",
            "problems": problems,
        }

    return {
        "ok": True,
        "schedule_id": schedule_id,
        "meetings": bell_schedules[schedule_id],
        "problems": problems,
    }


def get_day_schedule(date: str) -> dict:
    """Resolve teacher blocks for a specific date.

    No course gate, no student data — no safety gate.
    date: "YYYY-MM-DD" string
    Returns the canonical calendar's own resolution ``state`` (unconfigured,
    invalid_calendar, outside_coverage, no_school, no_regular_classes,
    unknown_schedule, or ready) alongside blocks: [{name, label, start, end,
    raw_periods, schedule_id, period_ids, segments, seq}, ...] sorted by
    start time. A repeated block produces one entry per consecutive meeting
    run; slides bind to its first entry.
    """
    result = deps.resolve_schedule_for(date)
    return {
        "ok": True,
        "date": date,
        "state": result["state"],
        "blocks": result["blocks"],
        "problems": result["problems"],
    }


def get_teacher_schedule() -> dict:
    """Read teacher schedule from workspace Calendars folder.

    No course gate, no student data — no safety gate.
    """
    teacher_schedule, problems = deps.load_teacher_schedule()
    return {
        "ok": True,
        "schedule": teacher_schedule,
        "problems": problems,
    }


def save_teacher_schedule(blocks: list) -> dict:
    """Replace the teacher's blocks in Teacher Schedule.json.

    This has no ``course_id`` parameter and makes no Canvas call. A
    teacher-set ``course_id`` field on a block passes through untouched after
    string validation. No student data, no course gate, no safety gate.
    Never raises.
    """
    if not isinstance(blocks, list):
        return {"ok": False, "problems": ["blocks must be a list"]}

    data, problems = schedule_setup.save_blocks(blocks)
    if data is None:
        return {"ok": False, "problems": problems}
    return {
        "ok": True,
        "count": len(blocks),
        "path": schedule_setup.teacher_schedule_path(),
    }


def get_school_calendar(date_from: str = "", date_to: str = "") -> dict:
    """Read the canonical School Calendar: readiness, plus a bounded range.

    No course_id, no student data -- no course gate, no safety gate.
    date_from/date_to: pass both for day/grading-period/event rows in that
    inclusive range; omit both for readiness only (revision, coverage,
    today's resolution, low-coverage warning). Never raises.
    """
    bell_schedules, _bell_problems = deps.load_bell_schedules()
    readiness = school_calendar.readiness(bell_schedule_ids=bell_schedules)
    result = {"ok": True, "readiness": readiness}
    if date_from and date_to:
        projection, problems = school_calendar.range_projection(date_from, date_to)
        if projection is None:
            return {"ok": False, "problems": problems}
        result["days"] = projection["days"]
        result["grading_periods"] = projection["grading_periods"]
        result["events"] = projection["events"]
    return result


def preview_school_calendar_replacement(school_year: str, coverage_start: str, coverage_end: str,
                                       default_schedule_id: str, weekday_schedules: dict = None,
                                       no_school_dates: list = None,
                                       no_regular_classes_dates: list = None,
                                       date_labels: dict = None, grading_periods: list = None,
                                       events: list = None) -> dict:
    """Preview a complete school-year create/replace. Never writes.

    No course_id, no student data -- no course gate, no safety gate.
    Returns a staged preview (operation, base_revision, current/proposed
    school year and coverage, material change counts, and a preview_digest)
    to summarize for the teacher before calling
    apply_school_calendar_replacement with its base_revision as
    expected_revision. Rejects an instructional date naming a Bell Schedule
    that is not currently loaded. Never raises.
    """
    bell_schedules, _bell_problems = deps.load_bell_schedules()
    preview, problems = school_calendar.preview_replacement(
        school_year=school_year, coverage_start=coverage_start, coverage_end=coverage_end,
        default_schedule_id=default_schedule_id, weekday_schedules=weekday_schedules,
        no_school_dates=no_school_dates, no_regular_classes_dates=no_regular_classes_dates,
        date_labels=date_labels, grading_periods=grading_periods, events=events,
        known_schedule_ids=set(bell_schedules),
    )
    if preview is None:
        return {"ok": False, "problems": problems}
    return {"ok": True, **preview}


def apply_school_calendar_replacement(preview: dict, expected_revision: int) -> dict:
    """Apply a preview returned by preview_school_calendar_replacement.

    No course_id, no student data -- no course gate, no safety gate. Pass the
    preview object back verbatim along with its base_revision as
    expected_revision; a stale revision or an altered preview digest is
    refused rather than silently written. Never raises.
    """
    doc, problems = school_calendar.apply_replacement(preview, expected_revision=expected_revision)
    if doc is None:
        return {"ok": False, "problems": problems}
    return {"ok": True, "revision": doc["revision"], "school_year": doc["school_year"],
            "coverage": doc["coverage"], "day_count": len(doc["days"])}


def preview_school_calendar_change(kind: str, schedule_id: str = "", label: str = "",
                                   dates: list = None, date_from: str = "", date_to: str = "",
                                   weekdays: list = None) -> dict:
    """Preview a day-kind/schedule/label change against the live calendar.

    No course_id, no student data -- no course gate, no safety gate.
    Summarize the affected dates and any conflicts for the teacher before
    calling apply_school_calendar_change. Rejects an instructional new value
    naming a Bell Schedule that is not currently loaded. Never raises.
    """
    bell_schedules, _bell_problems = deps.load_bell_schedules()
    preview, problems = school_calendar.preview_change(
        kind=kind, schedule_id=(schedule_id or None), label=(label or None),
        dates=dates, date_from=(date_from or None), date_to=(date_to or None),
        weekdays=weekdays, known_schedule_ids=set(bell_schedules),
    )
    if preview is None:
        return {"ok": False, "problems": problems}
    return {"ok": True, **preview}


def apply_school_calendar_change(preview: dict, expected_revision: int) -> dict:
    """Apply a previously returned preview. Refuses a stale expected_revision.

    No course_id, no student data -- no course gate, no safety gate. Never raises.
    """
    doc, problems = school_calendar.apply_change(preview, expected_revision=expected_revision)
    if doc is None:
        return {"ok": False, "problems": problems}
    return {"ok": True, "revision": doc["revision"]}


def preview_school_calendar_event_change(action: str, event: dict = None,
                                        event_id: str = "") -> dict:
    """Preview a public-event upsert or delete in the canonical Calendar.

    ``action`` is ``upsert`` with one complete structured event, or ``delete``
    with its stable ``event_id``. No course ID, student data, or direct write.
    """
    preview, problems = school_calendar.preview_event_change(
        action=action, event=event, event_id=(event_id or None))
    if preview is None:
        return {"ok": False, "problems": problems}
    return {"ok": True, **preview}


def apply_school_calendar_event_change(preview: dict, expected_revision: int) -> dict:
    """Apply a previewed public-event change after the teacher accepts it."""
    doc, problems = school_calendar.apply_event_change(
        preview, expected_revision=expected_revision)
    if doc is None:
        return {"ok": False, "problems": problems}
    return {"ok": True, "revision": doc["revision"]}


# --- Scoring Packet MCP Tools (v22) ----------------------------------------

def _safe_bundle_path(session: dict) -> str:
    """Resolved on-disk path of a session's SAFE bundle, or "" when absent."""
    raw = (session.get("privacy_artifacts") or {}).get("safe_bundle") or ""
    if not raw:
        return ""
    resolved = workspace.extended_path(raw)
    return resolved if os.path.isfile(resolved) else ""


def list_scoring_sessions() -> dict:
    """List PowerGrader sessions that have a SAFE bundle, newest first.

    Returns {"ok": True, "sessions": {columns, rows}} where each row has
    (session_id, assignment_name, course_id, created, mode_label, total,
    scored, approved). Current courses only. Sessions whose bundle is missing
    from disk are left out rather than offered and then refused by
    get_scoring_packet. Session metadata only, so no safety gate is needed:
    nothing here is drawn from a student record. Never raises.
    """
    from api.powergrader import session_store

    active_course_ids = {str(c.get("id", "")) for c in config.active_courses()}
    rows = []

    for summary in session_store.list_session_summaries():
        if str(summary.get("course_id") or "") not in active_course_ids:
            continue
        # The summary carries neither bundle presence nor a scored count, so
        # the full session is read for the Current-course candidates only.
        session = session_store.load_session(str(summary.get("session_id") or ""))
        if not session or not _safe_bundle_path(session):
            continue
        students = session.get("students") or []
        rows.append([
            summary.get("session_id"),
            summary.get("assignment_name"),
            summary.get("course_id"),
            summary.get("created"),
            summary.get("mode_label"),
            summary.get("total", 0),
            sum(1 for st in students if st.get("ai_score") is not None),
            summary.get("approved", 0),
        ])

    return {
        "ok": True,
        "sessions": {"columns": list(_SCORING_SESSION_COLUMNS), "rows": rows},
    }


def get_scoring_packet(session_id: str, offset: int = 0, limit: int = 10,
                       include_context: bool = True) -> dict:
    """Retrieve a page of student responses from a PowerGrader session's SAFE bundle.

    Parameters:
    - session_id: PowerGrader session UUID
    - offset: starting row (default 0)
    - limit: rows to return (default 10)
    - include_context: if True, include contract text, rubric, shared materials

    Paging walks responses, not students: on a multi-item quiz one student
    holds several rows, so offset, limit, total and next_offset all count
    rows. students_total carries the distinct-student count separately.

    Returns a packet with:
    - packet_digest: bundle identity, required by stage_scores
    - items: {columns, rows} table of prompts, deduplicated by item_id
    - students: {columns, rows} table of (pseudonym, item_id, text)
    - total: scorable rows in the whole session
    - students_total: distinct students holding at least one scorable row
    - returned: rows in this page
    - next_offset: offset for the next page, absent on the final page
    - held: responses with no scorable text (media-only or empty)
    - held_pseudonyms: distinct pseudonyms holding at least one held response
    - included_context: bool (true if contract/rubric were included)
    - estimated_tokens: projected token count for this response

    Course-gated on the session's course_id. Refuses when:
    - session_id is not found
    - session has no SAFE bundle
    - teacher's course is not a Current course
    - the page projects over the token budget (retry with a smaller limit)

    Text-only (no media entries, no attachment filenames). Never raises.
    """
    from api.powergrader import session_store, scoring_packet as sp

    session = session_store.load_session(session_id)
    if not session:
        return {"ok": False, "error": "Session not found."}

    gate_err = _course_gate_check(str(session.get("course_id") or ""))
    if gate_err:
        return {"ok": False, "error": gate_err}

    bundle_path = _safe_bundle_path(session)
    if not bundle_path:
        return {"ok": False, "error": "Safe AI Packet student response bundle is missing."}

    try:
        with open(bundle_path, encoding="utf-8") as f:
            safe_bundle = json.load(f)
    except Exception as e:
        return {"ok": False, "error": f"Could not load Safe AI Packet bundle: {e}"}

    try:
        packet = sp.build_packet(
            session=session,
            safe_bundle=safe_bundle,
            offset=offset,
            limit=limit,
            include_context=include_context,
            rubric_text=session.get("rubric_text", ""),
            persona=session.get("persona"),
        )
    except sp.PacketTooLarge as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Could not build packet: {e}"}

    # build_packet hands back dict rows so the scan can walk into the response
    # text. Tabulating first would bury every cell in a list, where the
    # scanner's key-based walk cannot reach it.
    result = _pseudonym_gate(packet, _vault_factory())
    if result.get("ok"):
        result["items"] = _tabulate(result["items"], _PACKET_ITEM_COLUMNS)
        result["students"] = _tabulate(result["students"], _PACKET_STUDENT_COLUMNS)
    return result


def stage_scores(session_id: str, results: list, expected_packet_digest: str) -> dict:
    """Stage AI-generated scores into a PowerGrader session.

    Parameters:
    - session_id: PowerGrader session UUID
    - results: list of scoring dicts (each with pseudonym, item_id, score, feedback)
    - expected_packet_digest: SHA-256 from a prior get_scoring_packet call
      (prevents staging stale scores if the session has been re-run)

    Returns:
    - updated: count of students whose scores were merged
    - unresolved: count of results with unknown pseudonyms or validation errors
    - validation: verdict dict (ok, errors, warnings)
    - packet_digest: unchanged, echoed back from expected_packet_digest

    Scores land in the session's student records, awaiting teacher review
    in the PowerGrader queue. Does NOT post to Canvas, even if auto_post
    is enabled (teacher pushes manually via the queue).

    Course-gated on the session's course_id. Refuses when:
    - session_id is not found
    - teacher's course is not a Current course
    - expected_packet_digest does not match current bundle state (session re-run)

    Partial staging works: if 6 of 28 students are scored, updates those 6,
    leaves 22 untouched, returns warnings for unscored. Never raises.
    """
    from datetime import datetime

    from api.powergrader import import_results, scoring_packet as sp, session_actions, session_store

    # Same lock the web UI's import-results route takes, so a teacher working
    # the queue and an assistant staging over MCP cannot interleave a
    # read-modify-write on the same session file.
    with session_store.session_lock(session_id):
        session = session_store.load_session(session_id)
        if not session:
            return {"ok": False, "error": "Session not found."}

        gate_err = _course_gate_check(str(session.get("course_id") or ""))
        if gate_err:
            return {"ok": False, "error": gate_err}

        bundle_path = _safe_bundle_path(session)
        if not bundle_path:
            return {"ok": False, "error": "Safe AI Packet student response bundle is missing."}

        try:
            with open(bundle_path, encoding="utf-8") as f:
                safe_bundle = json.load(f)
        except Exception as e:
            return {"ok": False, "error": f"Could not load Safe AI Packet bundle: {e}"}

        if sp.packet_digest(session.get("session_id"), safe_bundle) != expected_packet_digest:
            return {
                "ok": False,
                "error": "Packet digest mismatch: the session has been re-run. "
                         "Retrieve the packet again with get_scoring_packet.",
            }

        try:
            results_text = json.dumps(results)
        except Exception as e:
            return {"ok": False, "error": f"Could not serialize results: {e}"}

        # Any push review the teacher already previewed was computed against
        # the scores about to be replaced. Drop it first, exactly as the
        # import-results route does, so a stale review cannot be pushed.
        session_actions.invalidate_pending_review(session)
        session_store.save_session(session)

        payload, _status_code = import_results.import_results_into_session(
            session_id=session_id,
            results_text=results_text,
            batch_id="",
            load_session=session_store.load_session,
            save_session=session_store.save_session,
            vault_factory=_vault_factory,
        )

        # Deliberately no autopush trigger here, unlike the route: a score the
        # teacher has not seen never reaches Canvas.
        if payload.get("ok"):
            session = session_store.load_session(session_id)
            if session:
                session["assistant_staged"] = {
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "updated": payload.get("updated", 0),
                }
                session_store.save_session(session)

    # Rebuilt field by field rather than passed through: the import payload
    # carries updated_user_ids, which are real Canvas ids.
    result = {
        "ok": payload.get("ok", False),
        "updated": payload.get("updated", 0),
        "unresolved": payload.get("unresolved", 0),
        "validation": payload.get("validation", {}),
        "packet_digest": expected_packet_digest,
    }

    if not result["ok"]:
        result["error"] = payload.get("error", "Import failed")

    return result
