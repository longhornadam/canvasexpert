"""CanvasMirror on-disk store — envelope-wrapped collections of Canvas facts.

Layout, under ``_System/Canvas Mirror/<course_id>/`` in the synced workspace:

  _sync.v1.json                    pass envelopes + delta watermarks
  roster.v1.json                   students + sections
  assignments.v1.json              slim Canvas-shaped assignment index
  submissions/<assignment_id>.v1.json   per-student current row + attempts

Conventions follow ``api/course_catalog.py``: versioned filenames, exact-key
validation, catalog-style envelopes, atomic same-directory replace, and
per-course in-process locks. Two deliberate simplifications, both justified
by design law #1 (the mirror is disposable, Canvas is truth): there is no
previous-file promotion, and an unreadable or invalid file is treated as
absent — the next sync pass rewrites it.

Attempt history is append-only within a living submission: a merge may add
attempts and update ``current``, but never drops an attempt while its
submission row is retained. Merges are idempotent so watermark-overlap
duplicates from the sync engine are harmless.

Pure stdlib + storage_support; no Canvas imports; offline-testable via the
``root=`` parameter every public function accepts.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from api.storage_support import atomic_write_json
from api.webui import workspace


MIRROR_VERSION = 1
SYNC_FILENAME = "_sync.v1.json"
ROSTER_FILENAME = "roster.v1.json"
ASSIGNMENTS_FILENAME = "assignments.v1.json"
SUBMISSIONS_DIRNAME = "submissions"

# Course lifecycle is a narrow, student-free scheduling scope.  It deliberately
# lives beside (rather than inside) _sync.v1.json: pass readers rely on that
# file's exact schema, while lifecycle has independent refresh and last-good
# semantics.
COURSE_CONTEXT_VERSION = 1
COURSE_CONTEXT_FILENAME = "course_context.v1.json"
COURSE_CONTEXT_STATES = {"current", "stale", "unavailable"}
LIFECYCLE_STATES = {"current", "concluded", "unknown"}
ENROLLMENT_STATES = {"active", "invited", "completed", "inactive"}
CONTEXT_ERROR_CODES = {"", "unauthorized", "forbidden", "not_found",
                       "rate_limited", "timeout", "connection",
                       "invalid_response", "storage"}

# Collection files are written only on successful acquisition, so their state
# is "current" (or "incomplete" when pagination dropped records). Failures are
# recorded in _sync.v1.json pass envelopes; old collection files just age.
COLLECTION_STATES = {"current", "incomplete"}
PASS_NAMES = ("full", "delta", "roster")
PASS_STATES = {"current", "stale", "unavailable"}

_ENVELOPE_KEYS = {"state", "last_success_at", "last_attempt_at", "error_code"}
_SYNC_KEYS = {"schema_version", "course_id", "passes", "watermarks"}
_WATERMARK_KEYS = {"submitted_since", "graded_since"}
_ROSTER_KEYS = {"schema_version", "course_id", "students", "sections"} | _ENVELOPE_KEYS
_ASSIGNMENTS_KEYS = {"schema_version", "course_id", "assignments"} | _ENVELOPE_KEYS
_SUBMISSIONS_KEYS = {"schema_version", "course_id", "assignment_id",
                     "submissions"} | _ENVELOPE_KEYS
_SUBMISSION_ENTRY_KEYS = {"current", "attempts"}
_COURSE_CONTEXT_KEYS = {
    "schema_version", "course_id", "state", "last_success_at",
    "last_attempt_at", "error_code", "lifecycle", "course_workflow_state",
    "course_concluded", "course_end_at", "term_end_at", "enrollment_states",
}

# New Quiz metadata-scope capability record (1.0beta slice 01a). Student-free:
# just enough to gate the sync_metadata fan-out per course. Kept as its own
# small file (same course_dir/course_lock/atomic-write conventions as the rest
# of this module) instead of widening _sync.v1.json, so this slice never has
# to bump MIRROR_VERSION or touch the exact-key validation every other reader
# of _sync.v1.json depends on.
NEW_QUIZ_CAPABILITY_VERSION = 1
NEW_QUIZ_CAPABILITY_FILENAME = "new_quiz_capability.v1.json"
CAPABILITY_STATES = {"supported", "restricted", "unknown"}  # "unsupported" reserved, unused
_CAPABILITY_KEYS = {"schema_version", "course_id", "capability", "last_probe_at",
                    "retry_after", "evidence"}
_EVIDENCE_KEYS = {"category", "consecutive_failures"}
_EVIDENCE_CATEGORIES = {"", "forbidden", "unauthorized"}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def age_hours(iso_z: str, now_iso_z: str | None = None) -> float | None:
    """Age of a store timestamp in hours, or None if empty/unparseable."""
    if not iso_z:
        return None
    try:
        then = datetime.strptime(iso_z, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        now = (datetime.strptime(now_iso_z, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
               if now_iso_z else datetime.now(timezone.utc))
    except ValueError:
        return None
    return (now - then).total_seconds() / 3600.0


# --- locks -------------------------------------------------------------------

_LOCKS_GUARD = threading.Lock()
_COURSE_LOCKS: dict[str, threading.RLock] = {}


def course_lock(course_id) -> threading.RLock:
    """In-process per-course lock (catalog pattern). Cross-process safety
    comes from atomic replace, not this lock."""
    with _LOCKS_GUARD:
        return _COURSE_LOCKS.setdefault(str(course_id), threading.RLock())


# --- paths (resolved at call time so tests can redirect the workspace) -------

def course_dir(course_id, root=None):
    return workspace.course_mirror_dir(course_id, root)


def sync_path(course_id, root=None):
    directory = course_dir(course_id, root)
    return os.path.join(directory, SYNC_FILENAME) if directory else None


def roster_path(course_id, root=None):
    directory = course_dir(course_id, root)
    return os.path.join(directory, ROSTER_FILENAME) if directory else None


def assignments_path(course_id, root=None):
    directory = course_dir(course_id, root)
    return os.path.join(directory, ASSIGNMENTS_FILENAME) if directory else None


def submissions_dir(course_id, root=None):
    directory = course_dir(course_id, root)
    return os.path.join(directory, SUBMISSIONS_DIRNAME) if directory else None


def submission_path(course_id, assignment_id, root=None):
    directory = submissions_dir(course_id, root)
    if not directory:
        return None
    return os.path.join(directory, f"{workspace.safe_id(assignment_id)}.v1.json")


def new_quiz_capability_path(course_id, root=None):
    directory = course_dir(course_id, root)
    return os.path.join(directory, NEW_QUIZ_CAPABILITY_FILENAME) if directory else None


def course_context_path(course_id, root=None):
    directory = course_dir(course_id, root)
    return os.path.join(directory, COURSE_CONTEXT_FILENAME) if directory else None


def _require_dir(course_id, root):
    directory = course_dir(course_id, root)
    if not directory:
        raise ValueError("workspace not configured — no mirror location")
    return directory


# --- validation ---------------------------------------------------------------

def _require_exact_keys(value, keys: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} keys are invalid")


def _validate_envelope(document: dict, label: str, states: set[str]) -> None:
    if document.get("state") not in states:
        raise ValueError(f"{label} state is invalid")
    for key in ("last_success_at", "last_attempt_at", "error_code"):
        if not isinstance(document.get(key), str):
            raise ValueError(f"{label} {key} is invalid")


def _validate_common(document: dict, keys: set[str], course_id, label: str) -> None:
    _require_exact_keys(document, keys, label)
    if document.get("schema_version") != MIRROR_VERSION:
        raise ValueError(f"{label} schema_version is unsupported")
    if str(document.get("course_id")) != str(course_id):
        raise ValueError(f"{label} course_id mismatch")
    _validate_envelope(document, label, COLLECTION_STATES)


def _valid_iso_z(value) -> bool:
    if value == "":
        return True
    if not isinstance(value, str):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def validate_roster(document: dict, course_id) -> dict:
    _validate_common(document, _ROSTER_KEYS, course_id, "roster")
    if not isinstance(document.get("students"), dict) or not isinstance(document.get("sections"), dict):
        raise ValueError("roster collections are invalid")
    return document


def validate_assignments(document: dict, course_id) -> dict:
    _validate_common(document, _ASSIGNMENTS_KEYS, course_id, "assignments")
    if not isinstance(document.get("assignments"), dict):
        raise ValueError("assignments collection is invalid")
    return document


def validate_submissions(document: dict, course_id, assignment_id) -> dict:
    _validate_common(document, _SUBMISSIONS_KEYS, course_id, "submissions")
    if str(document.get("assignment_id")) != str(assignment_id):
        raise ValueError("submissions assignment_id mismatch")
    entries = document.get("submissions")
    if not isinstance(entries, dict):
        raise ValueError("submissions collection is invalid")
    for user_id, entry in entries.items():
        _require_exact_keys(entry, _SUBMISSION_ENTRY_KEYS, f"submission {user_id}")
        if not isinstance(entry["current"], dict) or not isinstance(entry["attempts"], dict):
            raise ValueError(f"submission {user_id} shape is invalid")
    return document


def validate_new_quiz_capability(document: dict, course_id) -> dict:
    _require_exact_keys(document, _CAPABILITY_KEYS, "new quiz capability")
    if document.get("schema_version") != NEW_QUIZ_CAPABILITY_VERSION:
        raise ValueError("new quiz capability schema_version is unsupported")
    if str(document.get("course_id")) != str(course_id):
        raise ValueError("new quiz capability course_id mismatch")
    if document.get("capability") not in CAPABILITY_STATES:
        raise ValueError("new quiz capability state is invalid")
    for key in ("last_probe_at", "retry_after"):
        if not isinstance(document.get(key), str):
            raise ValueError(f"new quiz capability {key} is invalid")
    evidence = document.get("evidence")
    _require_exact_keys(evidence, _EVIDENCE_KEYS, "new quiz capability evidence")
    if evidence.get("category") not in _EVIDENCE_CATEGORIES:
        raise ValueError("new quiz capability evidence category is invalid")
    failures = evidence.get("consecutive_failures")
    if not isinstance(failures, int) or isinstance(failures, bool) or failures < 0:
        raise ValueError("new quiz capability evidence consecutive_failures is invalid")
    return document


def validate_course_context(document: dict, course_id) -> dict:
    """Validate the lifecycle scheduling record's exact student-free shape."""
    _require_exact_keys(document, _COURSE_CONTEXT_KEYS, "course context")
    if (not isinstance(document.get("schema_version"), int)
            or isinstance(document.get("schema_version"), bool)
            or document["schema_version"] != COURSE_CONTEXT_VERSION):
        raise ValueError("course context schema_version is unsupported")
    if not isinstance(document.get("course_id"), str) or document["course_id"] != str(course_id):
        raise ValueError("course context course_id mismatch")
    if document.get("state") not in COURSE_CONTEXT_STATES:
        raise ValueError("course context state is invalid")
    if document.get("error_code") not in CONTEXT_ERROR_CODES:
        raise ValueError("course context error_code is invalid")
    for key in ("last_success_at", "last_attempt_at", "course_end_at", "term_end_at"):
        if not _valid_iso_z(document.get(key)):
            raise ValueError(f"course context {key} is invalid")
    if document.get("lifecycle") not in LIFECYCLE_STATES:
        raise ValueError("course context lifecycle is invalid")
    if not isinstance(document.get("course_workflow_state"), str):
        raise ValueError("course context course_workflow_state is invalid")
    if not isinstance(document.get("course_concluded"), bool):
        raise ValueError("course context course_concluded is invalid")
    enrollment_states = document.get("enrollment_states")
    if (not isinstance(enrollment_states, list)
            or any(state not in ENROLLMENT_STATES for state in enrollment_states)
            or len(set(enrollment_states)) != len(enrollment_states)):
        raise ValueError("course context enrollment_states are invalid")
    return document


def validate_sync(document: dict, course_id) -> dict:
    _require_exact_keys(document, _SYNC_KEYS, "sync")
    if document.get("schema_version") != MIRROR_VERSION:
        raise ValueError("sync schema_version is unsupported")
    if str(document.get("course_id")) != str(course_id):
        raise ValueError("sync course_id mismatch")
    passes = document.get("passes")
    _require_exact_keys(passes, set(PASS_NAMES), "sync passes")
    for name in PASS_NAMES:
        _require_exact_keys(passes[name], _ENVELOPE_KEYS, f"sync pass {name}")
        _validate_envelope(passes[name], f"sync pass {name}", PASS_STATES)
    _require_exact_keys(document.get("watermarks"), _WATERMARK_KEYS, "sync watermarks")
    for key in _WATERMARK_KEYS:
        if not isinstance(document["watermarks"][key], str):
            raise ValueError(f"sync watermark {key} is invalid")
    return document


# --- read/write primitives -----------------------------------------------------

def _read_document(path, validator):
    """Read + validate, or None. The mirror is disposable (design law #1):
    a missing, unparseable, or invalid file is simply absent — the next sync
    pass rewrites it. Never raise out of a read."""
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            document = json.load(handle)
        return validator(document)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _write_document(path, document) -> dict:
    atomic_write_json(Path(path), document)
    return document


# --- normalizers (Canvas rows -> stored shapes) ---------------------------------

def normalize_student(user: dict) -> dict | None:
    """Keep exactly the fields existing consumers use (roster_service upsert,
    pseudonymize_roster). No emails, no avatars — privacy-lean at rest."""
    if not isinstance(user, dict) or user.get("id") in (None, ""):
        return None
    return {
        "id": str(user["id"]),
        "name": str(user.get("name") or ""),
        "sortable_name": str(user.get("sortable_name") or ""),
        "short_name": str(user.get("short_name") or ""),
        "sis_user_id": str(user.get("sis_user_id") or ""),
        "enrollments": [
            {"course_section_id": str(e.get("course_section_id") or "")}
            for e in (user.get("enrollments") or [])
            if isinstance(e, dict) and e.get("course_section_id")
        ],
    }


def normalize_assignment(row: dict) -> dict | None:
    """Slim Canvas-shaped index — exactly what build_snapshot and the mirror
    queries need. The authoring catalog stays the rich source."""
    if not isinstance(row, dict) or row.get("id") in (None, ""):
        return None
    return {
        "id": str(row["id"]),
        "name": str(row.get("name") or ""),
        "due_at": str(row.get("due_at") or ""),
        "points_possible": row.get("points_possible"),
        "published": bool(row.get("published", True)),
        "html_url": str(row.get("html_url") or ""),
        "submission_types": [str(t) for t in (row.get("submission_types") or [])],
        "updated_at": str(row.get("updated_at") or ""),
    }


def _attempt_record(entry: dict) -> dict | None:
    attempt = entry.get("attempt")
    submitted_at = entry.get("submitted_at")
    if not attempt or not submitted_at:
        return None
    return {
        "attempt": int(attempt),
        "submitted_at": str(submitted_at),
        "submission_type": str(entry.get("submission_type") or ""),
        "body": entry.get("body") if isinstance(entry.get("body"), str) else "",
        "attachment_names": [
            str(a.get("filename") or a.get("display_name") or "")
            for a in (entry.get("attachments") or [])
            if isinstance(a, dict)
        ],
    }


def _comment_record(entry: dict) -> dict:
    # author_role uses the same fallback chain as the work-registry
    # classifier (home_attention._author_role) so staff-authored comments
    # stay provably staff when served from the mirror. Role label only —
    # still no names, avatars, or attachments.
    author = entry.get("author") if isinstance(entry.get("author"), dict) else {}
    return {
        "author_id": str(entry.get("author_id") or ""),
        "author_role": str(entry.get("author_role") or entry.get("author_type")
                           or author.get("role") or author.get("type") or ""),
        "comment": str(entry.get("comment") or ""),
        "created_at": str(entry.get("created_at") or ""),
    }


def normalize_submission(row: dict) -> tuple[str, dict, dict] | None:
    """Map one Canvas submission row to ``(user_id, current, attempts)``.

    ``current`` keeps Canvas field names so mirror-backed queries can hand
    rows to existing consumers unchanged. ``attempts`` collects the row's
    ``submission_history`` (when fetched) plus the row itself, keyed by
    attempt number — so a delta fetched without history still records the
    newest attempt.
    """
    if not isinstance(row, dict) or row.get("user_id") in (None, ""):
        return None
    current = {
        "assignment_id": str(row.get("assignment_id") or ""),
        "user_id": str(row["user_id"]),
        "workflow_state": str(row.get("workflow_state") or ""),
        "submitted_at": row.get("submitted_at"),
        "graded_at": row.get("graded_at"),
        "score": row.get("score"),
        "grade": row.get("grade"),
        "late": bool(row.get("late")),
        "missing": bool(row.get("missing")),
        "excused": bool(row.get("excused")),
        "attempt": row.get("attempt"),
        "grade_matches_current_submission": row.get("grade_matches_current_submission"),
        "submission_type": str(row.get("submission_type") or ""),
        "body": row.get("body") if isinstance(row.get("body"), str) else "",
        "submission_comments": [
            _comment_record(entry) for entry in (row.get("submission_comments") or [])
            if isinstance(entry, dict)
        ],
    }
    attempts: dict[str, dict] = {}
    # The row itself first, then history — a history entry for the same
    # attempt is richer (attachments, exact body) and must win.
    for entry in [row] + list(row.get("submission_history") or []):
        record = _attempt_record(entry) if isinstance(entry, dict) else None
        if record is not None:
            attempts[str(record["attempt"])] = record
    return current["user_id"], current, attempts


# --- collection writers ----------------------------------------------------------

def _envelope(state: str, attempted_at: str) -> dict:
    return {"state": state, "last_success_at": attempted_at,
            "last_attempt_at": attempted_at, "error_code": ""}


def write_roster(course_id, users: list[dict], sections: dict, *,
                 root=None, attempted_at: str | None = None,
                 state: str = "current") -> dict:
    _require_dir(course_id, root)
    attempted_at = attempted_at or now_iso()
    students = {}
    for user in users or []:
        normalized = normalize_student(user)
        if normalized is not None:
            students[normalized["id"]] = normalized
    document = {
        "schema_version": MIRROR_VERSION,
        "course_id": str(course_id),
        **_envelope(state, attempted_at),
        "students": students,
        "sections": {str(k): str(v) for k, v in (sections or {}).items()},
    }
    with course_lock(course_id):
        return _write_document(roster_path(course_id, root),
                               validate_roster(document, course_id))


def write_assignments(course_id, rows: list[dict], *, root=None,
                      attempted_at: str | None = None,
                      state: str = "current") -> dict:
    _require_dir(course_id, root)
    attempted_at = attempted_at or now_iso()
    assignments = {}
    for row in rows or []:
        normalized = normalize_assignment(row)
        if normalized is not None:
            assignments[normalized["id"]] = normalized
    document = {
        "schema_version": MIRROR_VERSION,
        "course_id": str(course_id),
        **_envelope(state, attempted_at),
        "assignments": assignments,
    }
    with course_lock(course_id):
        return _write_document(assignments_path(course_id, root),
                               validate_assignments(document, course_id))


def merge_submissions(course_id, assignment_id, rows: list[dict], *,
                      root=None, attempted_at: str | None = None,
                      state: str = "current", replace: bool = False) -> dict:
    """Merge Canvas submission rows into one assignment's mirror file.

    ``replace=False`` (delta): upsert the incoming users, keep everyone else.
    ``replace=True`` (full pass): the incoming rows define the user set —
    users no longer present are pruned — but attempts of retained users are
    carried over (append-only survives the rewrite).
    Idempotent: replaying the same rows yields an identical document.
    """
    _require_dir(course_id, root)
    attempted_at = attempted_at or now_iso()
    with course_lock(course_id):
        existing = read_submissions(course_id, assignment_id, root=root)
        existing_entries = (existing or {}).get("submissions") or {}
        entries: dict[str, dict] = {} if replace else {
            user_id: {"current": dict(entry["current"]),
                      "attempts": dict(entry["attempts"])}
            for user_id, entry in existing_entries.items()
        }
        for row in rows or []:
            normalized = normalize_submission(row)
            if normalized is None:
                continue
            user_id, current, attempts = normalized
            previous = entries.get(user_id) or existing_entries.get(user_id) or {}
            merged_attempts = dict(previous.get("attempts") or {})
            merged_attempts.update(attempts)
            # A row fetched without submission_comments (delta; or a full
            # pass that omitted the include) must not erase comments a prior
            # pass already stored — carry them forward when this row is bare.
            if not current.get("submission_comments"):
                previous_current = previous.get("current") or {}
                if previous_current.get("submission_comments"):
                    current["submission_comments"] = previous_current["submission_comments"]
            entries[user_id] = {"current": current, "attempts": merged_attempts}
        document = {
            "schema_version": MIRROR_VERSION,
            "course_id": str(course_id),
            "assignment_id": str(assignment_id),
            **_envelope(state, attempted_at),
            "submissions": entries,
        }
        return _write_document(submission_path(course_id, assignment_id, root),
                               validate_submissions(document, course_id, assignment_id))


def prune_submission_files(course_id, keep_assignment_ids, *, root=None) -> list[str]:
    """Full-pass deletion true-up: remove mirror files for assignments that no
    longer exist in Canvas. Returns the removed assignment ids."""
    directory = submissions_dir(course_id, root)
    if not directory or not os.path.isdir(directory):
        return []
    keep = {f"{workspace.safe_id(a)}.v1.json" for a in keep_assignment_ids}
    removed = []
    with course_lock(course_id):
        for name in os.listdir(directory):
            if not name.endswith(".v1.json") or name in keep:
                continue
            try:
                os.remove(os.path.join(directory, name))
                removed.append(name[: -len(".v1.json")])
            except OSError:
                continue
    return sorted(removed)


# --- collection readers -----------------------------------------------------------

def read_roster(course_id, *, root=None) -> dict | None:
    return _read_document(roster_path(course_id, root),
                          lambda d: validate_roster(d, course_id))


def read_assignments(course_id, *, root=None) -> dict | None:
    return _read_document(assignments_path(course_id, root),
                          lambda d: validate_assignments(d, course_id))


def read_submissions(course_id, assignment_id, *, root=None) -> dict | None:
    return _read_document(submission_path(course_id, assignment_id, root),
                          lambda d: validate_submissions(d, course_id, assignment_id))


def list_submission_assignment_ids(course_id, *, root=None) -> list[str]:
    directory = submissions_dir(course_id, root)
    if not directory or not os.path.isdir(directory):
        return []
    return sorted(name[: -len(".v1.json")] for name in os.listdir(directory)
                  if name.endswith(".v1.json"))


# --- sync state --------------------------------------------------------------------

def default_sync(course_id) -> dict:
    empty = {"state": "unavailable", "last_success_at": "",
             "last_attempt_at": "", "error_code": ""}
    return {
        "schema_version": MIRROR_VERSION,
        "course_id": str(course_id),
        "passes": {name: dict(empty) for name in PASS_NAMES},
        "watermarks": {"submitted_since": "", "graded_since": ""},
    }


def read_sync(course_id, *, root=None) -> dict:
    document = _read_document(sync_path(course_id, root),
                              lambda d: validate_sync(d, course_id))
    return document if document is not None else default_sync(course_id)


def default_course_context(course_id) -> dict:
    return {
        "schema_version": COURSE_CONTEXT_VERSION,
        "course_id": str(course_id),
        "state": "unavailable",
        "last_success_at": "",
        "last_attempt_at": "",
        "error_code": "",
        "lifecycle": "unknown",
        "course_workflow_state": "",
        "course_concluded": False,
        "course_end_at": "",
        "term_end_at": "",
        "enrollment_states": [],
    }


def read_course_context(course_id, *, root=None) -> dict:
    """Return a valid lifecycle record, or the unavailable default.

    Corrupt/foreign files are intentionally treated as absent, like every
    other disposable mirror record.  This keeps a malformed lifecycle file
    from authorizing cadence suppression.
    """
    document = _read_document(course_context_path(course_id, root),
                              lambda d: validate_course_context(d, course_id))
    return document if document is not None else default_course_context(course_id)


def record_course_context(course_id, *, ok: bool, attempted_at: str | None = None,
                          error_code: str = "", lifecycle: str = "unknown",
                          course_workflow_state: str = "",
                          course_concluded: bool = False, course_end_at: str = "",
                          term_end_at: str = "", enrollment_states: list[str] | None = None,
                          root=None) -> dict:
    """Commit a lifecycle acquisition outcome without touching any other scope.

    On failure this changes only the context envelope.  The prior successful
    lifecycle proof remains available as stale context for conservative
    concluded-course cadence suppression.
    """
    _require_dir(course_id, root)
    attempted_at = attempted_at or now_iso()
    with course_lock(course_id):
        document = read_course_context(course_id, root=root)
        document["last_attempt_at"] = attempted_at
        if ok:
            document.update({
                "state": "current",
                "last_success_at": attempted_at,
                "error_code": "",
                "lifecycle": lifecycle,
                "course_workflow_state": course_workflow_state,
                "course_concluded": course_concluded,
                "course_end_at": course_end_at,
                "term_end_at": term_end_at,
                "enrollment_states": list(enrollment_states or []),
            })
        else:
            document["state"] = "stale" if document["last_success_at"] else "unavailable"
            document["error_code"] = error_code or "connection"
        return _write_document(course_context_path(course_id, root),
                               validate_course_context(document, course_id))


def default_new_quiz_capability(course_id) -> dict:
    return {
        "schema_version": NEW_QUIZ_CAPABILITY_VERSION,
        "course_id": str(course_id),
        "capability": "unknown",
        "last_probe_at": "",
        "retry_after": "",
        "evidence": {"category": "", "consecutive_failures": 0},
    }


def read_new_quiz_capability(course_id, *, root=None) -> dict:
    document = _read_document(new_quiz_capability_path(course_id, root),
                              lambda d: validate_new_quiz_capability(d, course_id))
    return document if document is not None else default_new_quiz_capability(course_id)


def write_new_quiz_capability(course_id, *, capability: str, last_probe_at: str,
                              retry_after: str = "", evidence_category: str = "",
                              consecutive_failures: int = 0, root=None) -> dict:
    """Persist the New Quiz metadata-scope capability record. Student-free:
    only the fields the locked design allows (capability, probe/retry
    timestamps, a sanitized evidence category + count) — never status text,
    response bodies, URLs, or quiz titles."""
    _require_dir(course_id, root)
    document = {
        "schema_version": NEW_QUIZ_CAPABILITY_VERSION,
        "course_id": str(course_id),
        "capability": capability,
        "last_probe_at": last_probe_at,
        "retry_after": retry_after,
        "evidence": {"category": evidence_category,
                     "consecutive_failures": int(consecutive_failures)},
    }
    with course_lock(course_id):
        return _write_document(new_quiz_capability_path(course_id, root),
                               validate_new_quiz_capability(document, course_id))


def record_pass(course_id, pass_name: str, *, ok: bool, error_code: str = "",
                attempted_at: str | None = None, watermarks: dict | None = None,
                root=None) -> dict:
    """Record one sync-pass outcome (catalog-style degradation: a failure
    after a prior success is 'stale', never-succeeded is 'unavailable').
    Watermarks are advanced only on success."""
    if pass_name not in PASS_NAMES:
        raise ValueError(f"unknown sync pass: {pass_name}")
    _require_dir(course_id, root)
    attempted_at = attempted_at or now_iso()
    with course_lock(course_id):
        document = read_sync(course_id, root=root)
        entry = document["passes"][pass_name]
        entry["last_attempt_at"] = attempted_at
        if ok:
            entry["state"] = "current"
            entry["last_success_at"] = attempted_at
            entry["error_code"] = ""
            if watermarks:
                for key in _WATERMARK_KEYS:
                    if key in watermarks:
                        document["watermarks"][key] = str(watermarks[key])
        else:
            entry["state"] = "stale" if entry["last_success_at"] else "unavailable"
            entry["error_code"] = error_code or "sync_failed"
        return _write_document(sync_path(course_id, root),
                               validate_sync(document, course_id))
