"""Offline tests for the read-only MCP server's tool implementations.

Vault is isolated to ``tmp_path`` per test (never the real global vault).
Fabricated data uses generic names ("Learner One") and large made-up Canvas
IDs, never a specific pseudonym assertion (pseudonym assignment is random).
Worktree-independent: paths are computed from ``__file__``, never hardcoded.

Mirrors the monkeypatch-module-level-fetchers pattern from
``api/tests/test_gradebook_routes.py``.
"""
from __future__ import annotations

import json
import os
import sys

# api/mcp_server/pseudonym.py reaches api.webui.routes.names, which (like the
# rest of the webui package) imports sibling top-level api/ modules with bare
# names ("import feedback_scrub"). That only resolves once the api/ directory
# itself is on sys.path -- normally guaranteed by api/mcp_server/__main__.py's
# bootstrap at runtime. Standalone test collection needs the same bootstrap.
_API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_API_DIR)
for _path in (_API_DIR, _REPO_ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from api import feedback_safety, gradebook_queries, roster_service
from api.feedback_vault import Vault
from api.mcp_server import pseudonym, tools
from api.mirror import store as mirror_store
from api.webui import workspace

FIXTURE_USERS = [
    {
        "id": 900001,
        "name": "Learner One",
        "sortable_name": "One, Learner",
        "short_name": "Lee",
        "sis_user_id": "SIS-900001",
        "enrollments": [{"course_section_id": 800001}],
    },
    {
        "id": 900002,
        "name": "Learner Two",
        "sortable_name": "Two, Learner",
        "short_name": "Learner Two",
        "sis_user_id": "SIS-900002",
        "enrollments": [{"course_section_id": 800002}],
    },
]
SECTION_MAP = {"800001": "Period 1", "800002": "Period 2"}

GRADEBOOK_STUDENTS = [
    {"id": 900001, "name": "Learner One", "sortable_name": "One, Learner"},
    {"id": 900002, "name": "Learner Two", "sortable_name": "Two, Learner"},
]
GRADEBOOK_ASSIGNMENTS = [{
    "id": 700010, "name": "Quiz 1", "due_at": "2026-07-01T23:59:00Z",
    "points_possible": 10, "html_url": "https://example.invalid/quiz-1",
    "published": True,
}]
GRADEBOOK_SUBS = [
    {"assignment_id": 700010, "user_id": 900001, "workflow_state": "graded",
     "score": 9, "submitted_at": "2026-07-01T20:00:00Z"},
    {"assignment_id": 700010, "user_id": 900002, "workflow_state": "submitted",
     "submitted_at": "2026-07-01T21:00:00Z"},
]

_LEAKS = [
    "Learner One", "Learner Two", "One, Learner", "Two, Learner", "Lee",
    "900001", "900002", "SIS-900001", "SIS-900002",
]


def _assert_no_leaks(payload: dict):
    dumped = json.dumps(payload)
    for leak in _LEAKS:
        assert leak not in dumped, f"{leak!r} leaked into payload: {dumped}"


def _rows(table: dict) -> list[dict]:
    """Re-expand a token-lean {columns, rows} table into per-row dicts."""
    return [dict(zip(table["columns"], row)) for row in table["rows"]]


def _use_vault(monkeypatch, tmp_path) -> str:
    vault_path = str(tmp_path / "vault.json")
    monkeypatch.setattr(tools, "_vault_factory", lambda: Vault(vault_path))
    return vault_path


def _set_active_courses(monkeypatch, course_ids):
    monkeypatch.setattr(
        tools.config, "active_courses",
        lambda: [{"id": cid, "name": f"Course {cid}"} for cid in course_ids],
    )


# --- list_courses (no course_id, no student data -> no gates) --------------

def test_list_courses_happy(monkeypatch):
    monkeypatch.setattr(tools.config, "saved_courses", lambda: [
        {"id": "111", "name": "Algebra I", "nickname": "", "active": True},
        {"id": "222", "name": "Geometry", "nickname": "Geo Honors", "active": False},
    ])
    result = tools.list_courses()
    assert result == {"ok": True, "courses": [
        {"course_id": "111", "course_name": "Algebra I", "active": True},
        {"course_id": "222", "course_name": "Geo Honors", "active": False},
    ]}


def test_list_courses_empty(monkeypatch):
    monkeypatch.setattr(tools.config, "saved_courses", lambda: [])
    assert tools.list_courses() == {"ok": True, "courses": []}


# --- course gating (shared by every course_id tool) -------------------------

def test_course_gate_check_rejects_non_current_course(monkeypatch):
    monkeypatch.setattr(tools.config, "active_courses", lambda: [{"id": "111"}])
    assert tools._course_gate_check("999") is not None
    assert tools._course_gate_check("111") is None


def test_get_roster_rejects_non_current_course(monkeypatch, tmp_path):
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["222"])
    result = tools.get_roster("111")
    assert result["ok"] is False
    assert "not a Current course" in result["error"]


def test_student_tools_fail_closed_when_workspace_unresolved(monkeypatch):
    """When the workspace (and thus the identity vault) can't be resolved, the
    student-data tools must refuse rather than scatter the vault to a stray path.
    No _vault_factory override here: this exercises the real _default_vault."""
    _set_active_courses(monkeypatch, ["111"])
    monkeypatch.setattr(workspace, "identity_vault_dir", lambda *a, **k: None)
    monkeypatch.setattr(workspace, "feedback_folder", lambda *a, **k: None)
    for result in (
        tools.get_roster("111"),
        tools.get_submissions("111", "700010"),
        tools.get_gradebook_snapshot("111"),
    ):
        assert result["ok"] is False
        assert "workspace" in result["error"].lower()


# --- get_course_assignments (disk-only catalog, no student data) -----------

def _catalog_document(assignment_records, module_records):
    scope = {"state": "current", "last_success_at": "2026-07-01T00:00:00Z",
             "last_attempt_at": "2026-07-01T00:00:00Z", "error_code": ""}
    return {
        "course_id": "111",
        "course_name": "Test Course",
        "updated_at": "2026-07-01T00:00:00Z",
        "assignments": {**scope, "records": assignment_records},
        "modules": {**scope, "records": module_records},
    }


def test_get_course_assignments_happy(monkeypatch):
    _set_active_courses(monkeypatch, ["111"])
    document = _catalog_document(
        {"700010": {"id": 700010, "name": "Quiz 1", "description_text": "desc",
                    "points_possible": 10, "due_at": "2026-07-01T23:59:00Z",
                    "published": True}},
        [],
    )
    monkeypatch.setattr(tools, "read_catalog",
                        lambda course_id: {"catalog": document, "source": "canonical", "warnings": []})

    result = tools.get_course_assignments("111")
    assert result["ok"] is True
    assert result["course_name"] == "Test Course"
    assert _rows(result["assignments"]) == [{
        "id": 700010, "title": "Quiz 1", "description_text": "desc",
        "due_at": "2026-07-01T23:59:00Z", "points_possible": 10, "published": True,
    }]


def test_get_course_assignments_uses_catalog_read_scope(monkeypatch):
    _set_active_courses(monkeypatch, ["111"])
    document = _catalog_document(
        {"700010": {"id": 700010, "name": "Quiz 1", "description_text": "desc",
                    "points_possible": 10, "due_at": "", "published": True}},
        [],
    )
    read_result = {"catalog": document, "source": "canonical", "warnings": []}
    calls = []
    monkeypatch.setattr(tools, "read_catalog", lambda course_id: read_result)

    def catalog_assignments(course_id, *, catalog_reader=None):
        calls.append(course_id)
        assert catalog_reader(course_id) is read_result
        return {
            "source": "catalog", "records": list(document["assignments"]["records"].values()),
        }

    monkeypatch.setattr(tools.read_service, "catalog_assignments", catalog_assignments)

    assert tools.get_course_assignments("111")["ok"] is True
    assert calls == ["111"]


def test_get_course_assignments_trims_long_descriptions(monkeypatch):
    _set_active_courses(monkeypatch, ["111"])
    long_description = "word " * 200  # 1000 chars, well past the preview cut
    document = _catalog_document(
        {"700010": {"id": 700010, "name": "Quiz 1",
                    "description_text": long_description,
                    "points_possible": 10, "due_at": "2026-07-01T23:59:00Z",
                    "published": True}},
        [],
    )
    monkeypatch.setattr(tools, "read_catalog",
                        lambda course_id: {"catalog": document, "source": "canonical", "warnings": []})

    preview = _rows(tools.get_course_assignments("111")["assignments"])[0]["description_text"]
    assert len(preview) < len(long_description)
    assert preview.startswith(long_description[:tools._DESCRIPTION_PREVIEW_CHARS])
    assert "truncated" in preview

    full = _rows(tools.get_course_assignments("111", full_descriptions=True)
                 ["assignments"])[0]["description_text"]
    assert full == long_description


def test_get_course_assignments_empty(monkeypatch):
    _set_active_courses(monkeypatch, ["111"])
    document = _catalog_document({}, [{"id": 1, "name": "Module 1", "position": 1, "items": []}])
    monkeypatch.setattr(tools, "read_catalog",
                        lambda course_id: {"catalog": document, "source": "canonical", "warnings": []})

    result = tools.get_course_assignments("111")
    assert result["ok"] is True
    assert result["course_id"] == "111"
    assert result["course_name"] == "Test Course"
    assert result["assignments"]["rows"] == []


def test_get_course_assignments_catalog_missing(monkeypatch):
    _set_active_courses(monkeypatch, ["111"])
    monkeypatch.setattr(tools, "read_catalog",
                        lambda course_id: {"catalog": None, "source": "none", "warnings": []})

    result = tools.get_course_assignments("111")
    assert result["ok"] is False
    assert "refresh" in result["error"].lower()


def test_get_course_assignments_rejects_non_current_course(monkeypatch):
    _set_active_courses(monkeypatch, ["222"])
    result = tools.get_course_assignments("111")
    assert result["ok"] is False
    assert "not a Current course" in result["error"]


# --- get_roster --------------------------------------------------------------

def test_get_roster_happy(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    mirror_store.write_roster("111", FIXTURE_USERS, SECTION_MAP, root=str(tmp_path))

    result = tools.get_roster("111")
    assert result["ok"] is True
    assert result["source"] == "mirror"
    assert result["roster"]["columns"] == ["pseudonym", "section_names"]
    roster = _rows(result["roster"])
    assert len(roster) == 2
    pseudonyms = {row["pseudonym"] for row in roster}
    assert len(pseudonyms) == 2  # each student gets a distinct pseudonym
    section_sets = {tuple(row["section_names"]) for row in roster}
    assert section_sets == {("Period 1",), ("Period 2",)}
    assert roster == sorted(roster, key=lambda r: r["pseudonym"])  # sorted by pseudonym
    _assert_no_leaks(result)


def test_get_roster_empty(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    mirror_store.write_roster("111", [], {}, root=str(tmp_path))

    result = tools.get_roster("111")
    assert result["ok"] is True
    assert result["roster"]["rows"] == []


def test_get_roster_failure(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    # No mirror seeded at all: refused rather than fetched live.

    assert tools.get_roster("111") == {"ok": False, "error": tools._MIRROR_UNAVAILABLE_ROSTER_ERROR}


# --- get_submissions ----------------------------------------------------------

def test_get_submissions_happy_scrubs_real_name_and_short_name(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    root = str(tmp_path)
    mirror_store.write_roster("111", FIXTURE_USERS, SECTION_MAP, root=root)
    mirror_store.write_assignments("111", [MIRROR_ASSIGNMENT], root=root)
    mirror_store.merge_submissions("111", "700010", [
        {"assignment_id": 700010, "user_id": 900001, "workflow_state": "graded", "score": 9,
         "grade": "9", "submitted_at": "2026-07-01T20:00:00Z", "late": False, "missing": False,
         "excused": False, "body": "<p>Learner One and Lee worked together on this.</p>"},
    ], root=root, replace=True)
    mirror_store.record_pass("111", "full", ok=True, root=root)

    result = tools.get_submissions("111", "700010")
    assert result["ok"] is True
    assert result["assignment"] == {
        "id": "700010", "title": "Essay 1", "points_possible": 10, "due_at": "2026-07-01T23:59:00Z",
    }
    subs = _rows(result["submissions"])
    assert len(subs) == 1
    row = subs[0]
    assert row["workflow_state"] == "graded"
    assert row["score"] == 9
    # Both the legal name ("Learner One") and the short_name nickname ("Lee")
    # come back as the SAME pseudonym -- the whole point of nickname capture.
    pseudo_first = row["pseudonym"].split()[0]
    assert row["pseudonym"] in row["text"]
    assert pseudo_first in row["text"]
    _assert_no_leaks(result)


def _submissions_fixture(monkeypatch, tmp_path, bodies_by_user=None):
    bodies_by_user = bodies_by_user or {
        900001: "<p>First essay body.</p>",
        900002: "<p>Second essay body.</p>",
    }
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    root = str(tmp_path)
    mirror_store.write_roster("111", FIXTURE_USERS, SECTION_MAP, root=root)
    mirror_store.write_assignments("111", [
        {"id": 700010, "name": "Essay 1", "points_possible": 10, "due_at": ""},
    ], root=root)
    mirror_store.merge_submissions("111", "700010", [
        {"assignment_id": 700010, "user_id": uid, "workflow_state": "submitted",
         "submitted_at": "2026-07-01T20:00:00Z", "body": body}
        for uid, body in bodies_by_user.items()
    ], root=root, replace=True)
    mirror_store.record_pass("111", "full", ok=True, root=root)


def test_get_submissions_include_text_false_drops_text_column(monkeypatch, tmp_path):
    _submissions_fixture(monkeypatch, tmp_path)
    result = tools.get_submissions("111", "700010", include_text=False)
    assert result["ok"] is True
    assert "text" not in result["submissions"]["columns"]
    assert len(result["submissions"]["rows"]) == 2
    dumped = json.dumps(result)
    assert "essay body" not in dumped


def test_get_submissions_pseudonyms_filter_narrows_rows(monkeypatch, tmp_path):
    _submissions_fixture(monkeypatch, tmp_path)
    everyone = _rows(tools.get_submissions("111", "700010")["submissions"])
    assert len(everyone) == 2
    target = everyone[0]["pseudonym"]

    # Case-insensitive, tolerant of spaces around the comma.
    filtered = tools.get_submissions("111", "700010", pseudonyms=f" {target.upper()} ,")
    rows = _rows(filtered["submissions"])
    assert [row["pseudonym"] for row in rows] == [target]


def test_get_submissions_max_text_chars_truncates_with_marker(monkeypatch, tmp_path):
    long_body = "<p>" + ("sentence " * 100) + "</p>"  # ~900 chars of text
    _submissions_fixture(monkeypatch, tmp_path, {900001: long_body})

    result = tools.get_submissions("111", "700010", max_text_chars=100)
    row = _rows(result["submissions"])[0]
    assert len(row["text"]) < 200
    assert "truncated" in row["text"]

    untrimmed = tools.get_submissions("111", "700010", max_text_chars=0)
    full_row = _rows(untrimmed["submissions"])[0]
    assert "truncated" not in full_row["text"]
    assert len(full_row["text"]) > 800


def test_get_submissions_empty(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    root = str(tmp_path)
    mirror_store.write_roster("111", FIXTURE_USERS, SECTION_MAP, root=root)
    mirror_store.write_assignments("111", [
        {"id": 700010, "name": "Essay 1", "points_possible": 10, "due_at": ""},
    ], root=root)
    mirror_store.merge_submissions("111", "700010", [], root=root, replace=True)
    mirror_store.record_pass("111", "full", ok=True, root=root)

    result = tools.get_submissions("111", "700010")
    assert result["ok"] is True
    assert result["submissions"]["rows"] == []


def test_get_submissions_failure(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    root = str(tmp_path)
    # Fresh mirror (roster + a DIFFERENT assignment) -- "700010" just isn't in
    # it, a distinct non-staleness error from the mirror-unavailable refusal.
    mirror_store.write_roster("111", FIXTURE_USERS, SECTION_MAP, root=root)
    mirror_store.write_assignments("111", [
        {"id": 700099, "name": "Other Assignment", "points_possible": 10, "due_at": ""},
    ], root=root)
    mirror_store.record_pass("111", "full", ok=True, root=root)

    assert tools.get_submissions("111", "700010") == {
        "ok": False, "error": "No such assignment in this course's local catalog."}


def test_get_submissions_rejects_non_current_course(monkeypatch, tmp_path):
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["222"])
    result = tools.get_submissions("111", "700010")
    assert result["ok"] is False
    assert "not a Current course" in result["error"]


# --- typed mirror-first reads (1.0beta-05) ------------------------------------
#
# roster/assignment/submission acquisition now goes through the typed local
# read service (api/mirror/read_service.py) instead of owning mirror
# store/query calls directly. These tests populate a real on-disk mirror
# (workspace root redirected to tmp_path, same fixture style as
# api/tests/test_mirror_reads_helper.py) and prove (a) a fresh mirror serves
# both get_roster and get_submissions with zero live Canvas calls, and (b)
# any one of the three required scopes (roster, assignments, submissions)
# being stale falls the WHOLE submission bundle back to live as one coherent
# read -- never a partial mirror/live mix.

MIRROR_COURSE = "111"
MIRROR_ASSIGNMENT = {
    "id": 700010, "name": "Essay 1", "due_at": "2026-07-01T23:59:00Z",
    "points_possible": 10, "published": True, "html_url": "https://example.invalid/essay",
}
MIRROR_SUBMISSIONS = [
    {"assignment_id": 700010, "user_id": 900001, "workflow_state": "graded",
     "score": 9, "grade": "9", "submitted_at": "2026-07-01T20:00:00Z",
     "late": False, "missing": False, "excused": False,
     "body": "<p>Learner One and Lee worked together on this.</p>"},
    {"assignment_id": 700010, "user_id": 900002, "workflow_state": "submitted",
     "submitted_at": "2026-07-01T21:00:00Z", "body": "<p>Second submission body.</p>"},
]
_STALE_STAMP = "2000-01-01T00:00:00Z"


def _mount_mirror(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))


def _populate_mirror(root, *, roster_at=None, assignments_at=None, submissions_at=None):
    fresh = mirror_store.now_iso()
    roster_at = roster_at or fresh
    assignments_at = assignments_at or fresh
    submissions_at = submissions_at or fresh
    mirror_store.write_roster(MIRROR_COURSE, FIXTURE_USERS, SECTION_MAP,
                              root=root, attempted_at=roster_at)
    mirror_store.write_assignments(MIRROR_COURSE, [MIRROR_ASSIGNMENT],
                                   root=root, attempted_at=assignments_at)
    mirror_store.merge_submissions(MIRROR_COURSE, "700010", MIRROR_SUBMISSIONS,
                                   root=root, attempted_at=submissions_at, replace=True)
    mirror_store.record_pass(MIRROR_COURSE, "full", ok=True,
                             attempted_at=submissions_at, root=root)


def _explode_live(*_args, **_kwargs):
    raise AssertionError("live Canvas read attempted")


def test_get_roster_serves_fresh_typed_mirror_with_zero_live_calls(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, [MIRROR_COURSE])
    _populate_mirror(str(tmp_path))
    monkeypatch.setattr(tools, "_canvas_get_all", _explode_live)

    result = tools.get_roster(MIRROR_COURSE)
    assert result["ok"] is True
    assert result["source"] == "mirror"
    assert result["synced_at"]
    roster = _rows(result["roster"])
    assert len(roster) == 2
    section_sets = {tuple(row["section_names"]) for row in roster}
    assert section_sets == {("Period 1",), ("Period 2",)}
    _assert_no_leaks(result)


def test_get_submissions_serves_fresh_typed_mirror_with_zero_live_calls(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, [MIRROR_COURSE])
    _populate_mirror(str(tmp_path))
    monkeypatch.setattr(tools, "_canvas_get_all", _explode_live)

    result = tools.get_submissions(MIRROR_COURSE, "700010")
    assert result["ok"] is True
    assert result["source"] == "mirror"
    assert result["synced_at"]
    assert result["assignment"]["title"] == "Essay 1"
    subs = _rows(result["submissions"])
    assert len(subs) == 2  # locally filtered to just this assignment's rows
    _assert_no_leaks(result)


def test_get_submissions_refuses_when_roster_stale(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, [MIRROR_COURSE])
    _populate_mirror(str(tmp_path), roster_at=_STALE_STAMP)
    monkeypatch.setattr(gradebook_queries, "assignment", _explode_live)
    monkeypatch.setattr(gradebook_queries, "assignment_submissions", _explode_live)
    monkeypatch.setattr(roster_service, "fetch_students", _explode_live)

    assert tools._mirror_submission_bundle(MIRROR_COURSE, "700010") == (None, None)
    result = tools.get_submissions(MIRROR_COURSE, "700010")
    assert result == {"ok": False, "error": tools._MIRROR_UNAVAILABLE_SUBMISSIONS_ERROR}


def test_get_submissions_refuses_when_assignments_stale(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, [MIRROR_COURSE])
    _populate_mirror(str(tmp_path), assignments_at=_STALE_STAMP)
    monkeypatch.setattr(gradebook_queries, "assignment", _explode_live)
    monkeypatch.setattr(gradebook_queries, "assignment_submissions", _explode_live)
    monkeypatch.setattr(roster_service, "fetch_students", _explode_live)

    assert tools._mirror_submission_bundle(MIRROR_COURSE, "700010") == (None, None)
    result = tools.get_submissions(MIRROR_COURSE, "700010")
    assert result == {"ok": False, "error": tools._MIRROR_UNAVAILABLE_SUBMISSIONS_ERROR}


def test_get_submissions_refuses_when_submissions_stale(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, [MIRROR_COURSE])
    _populate_mirror(str(tmp_path), submissions_at=_STALE_STAMP)
    monkeypatch.setattr(gradebook_queries, "assignment", _explode_live)
    monkeypatch.setattr(gradebook_queries, "assignment_submissions", _explode_live)
    monkeypatch.setattr(roster_service, "fetch_students", _explode_live)

    assert tools._mirror_submission_bundle(MIRROR_COURSE, "700010") == (None, None)
    result = tools.get_submissions(MIRROR_COURSE, "700010")
    assert result == {"ok": False, "error": tools._MIRROR_UNAVAILABLE_SUBMISSIONS_ERROR}


# --- get_gradebook_snapshot ---------------------------------------------------

def test_get_gradebook_snapshot_happy(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    root = str(tmp_path)
    mirror_store.write_roster("111", GRADEBOOK_STUDENTS, {}, root=root)
    mirror_store.write_assignments("111", GRADEBOOK_ASSIGNMENTS, root=root)
    mirror_store.merge_submissions("111", "700010", GRADEBOOK_SUBS, root=root, replace=True)
    for pass_name in ("full", "roster"):
        mirror_store.record_pass("111", pass_name, ok=True, root=root)

    result = tools.get_gradebook_snapshot("111")
    assert result["ok"] is True
    assert result["class_avg"] == 90.0
    assert result["student_count"] == 2
    assert _rows(result["assignments"]) == [{
        "id": "700010", "title": "Quiz 1", "due_at": "2026-07-01",
        "points": 10, "submitted": 2, "graded": 1, "missing": 0, "late": 0, "avg_pct": 90,
    }]
    assert result["students"]["columns"] == ["pseudonym", "missing", "late", "ungraded", "pct"]
    assert len(result["students"]["rows"]) == 2
    _assert_no_leaks(result)


def test_get_gradebook_snapshot_empty(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    root = str(tmp_path)
    mirror_store.write_roster("111", [], {}, root=root)
    mirror_store.write_assignments("111", [], root=root)
    mirror_store.merge_submissions("111", "700010", [], root=root, replace=True)
    for pass_name in ("full", "roster"):
        mirror_store.record_pass("111", pass_name, ok=True, root=root)

    result = tools.get_gradebook_snapshot("111")
    assert result["ok"] is True
    assert result["class_avg"] is None
    assert result["student_count"] == 0
    assert result["assignments"]["rows"] == []
    assert result["students"]["rows"] == []


def test_get_gradebook_snapshot_failure(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    # No mirror seeded at all: a whole-course snapshot is refused, never live.

    assert tools.get_gradebook_snapshot("111") == {
        "ok": False, "error": tools._MIRROR_UNAVAILABLE_SNAPSHOT_ERROR}


def test_get_gradebook_snapshot_rejects_non_current_course(monkeypatch, tmp_path):
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["222"])
    result = tools.get_gradebook_snapshot("111")
    assert result["ok"] is False
    assert "not a Current course" in result["error"]


# --- pseudonym round trip -----------------------------------------------------

def test_pseudonym_reverse_round_trip(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    vault_path = _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    mirror_store.write_roster("111", FIXTURE_USERS, SECTION_MAP, root=str(tmp_path))

    result = tools.get_roster("111")
    assert result["ok"] is True
    pseudonym_value = _rows(result["roster"])[0]["pseudonym"]

    fresh_vault = Vault(vault_path)  # re-open from disk, not the in-memory instance
    reversed_entry = fresh_vault.reverse(pseudonym_value)
    assert reversed_entry is not None
    assert reversed_entry["real_name"] in {"Learner One", "Learner Two"}
    assert reversed_entry["canvas_id"] in {"900001", "900002"}


# --- no-PII sweep + scan_payload green ---------------------------------------

def test_no_pii_sweep_and_scan_payload_green(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    vault_path = _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    root = str(tmp_path)
    mirror_store.write_roster("111", GRADEBOOK_STUDENTS, {}, root=root)
    mirror_store.write_assignments("111", GRADEBOOK_ASSIGNMENTS, root=root)
    mirror_store.merge_submissions("111", "700010", GRADEBOOK_SUBS, root=root, replace=True)
    for pass_name in ("full", "roster"):
        mirror_store.record_pass("111", pass_name, ok=True, root=root)

    result = tools.get_gradebook_snapshot("111")
    assert result["ok"] is True
    _assert_no_leaks(result)

    fresh_vault = Vault(vault_path)
    verdict = feedback_safety.scan_payload(result, fresh_vault)
    assert verdict["green"] is True
    assert verdict["hard"] == []


def test_no_pii_sweep_scan_payload_green_for_submissions(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    vault_path = _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    root = str(tmp_path)
    mirror_store.write_roster("111", FIXTURE_USERS, SECTION_MAP, root=root)
    mirror_store.write_assignments("111", [MIRROR_ASSIGNMENT], root=root)
    mirror_store.merge_submissions("111", "700010", [
        {"assignment_id": 700010, "user_id": 900001, "workflow_state": "graded", "score": 9,
         "grade": "9", "submitted_at": "2026-07-01T20:00:00Z", "late": False, "missing": False,
         "excused": False, "body": "<p>Learner One and Lee worked together on this.</p>"},
    ], root=root, replace=True)
    mirror_store.record_pass("111", "full", ok=True, root=root)

    result = tools.get_submissions("111", "700010")
    assert result["ok"] is True

    fresh_vault = Vault(vault_path)
    verdict = feedback_safety.scan_payload(result, fresh_vault)
    assert verdict["green"] is True
    assert verdict["hard"] == []
    assert verdict["soft"] == []  # the scrub caught every roster name; nothing left to flag


# --- gate fail-closed ---------------------------------------------------------

def test_gate_fails_closed_on_leaking_identity_key(tmp_path):
    vault = Vault(str(tmp_path / "vault.json"))
    vault.get_or_assign("900001", "Leaked Real Name", "SIS-900001")

    leaking_payload = {"roster": [{"pseudonym": "Whatever Fake Name", "name": "Leaked Real Name"}]}
    result = pseudonym.gate(leaking_payload, vault)

    assert result["ok"] is False
    assert set(result.keys()) == {"ok", "error", "violations"}
    assert result["violations"]
    dumped = json.dumps(result)
    assert "Leaked Real Name" not in dumped
    assert "SIS-900001" not in dumped


def test_gate_passes_clean_payload_through(tmp_path):
    vault = Vault(str(tmp_path / "vault.json"))
    clean_payload = {"roster": [{"pseudonym": "Whatever Fake Name", "section_names": ["Period 1"]}]}
    result = pseudonym.gate(clean_payload, vault)
    assert result == {"ok": True, **clean_payload}


# --- refresh_mirror -------------------------------------------------------------

def test_refresh_mirror_rejects_non_current_course(monkeypatch):
    _set_active_courses(monkeypatch, ["222"])
    result = tools.refresh_mirror("111")
    assert result["ok"] is False
    assert "not a Current course" in result["error"]


def test_refresh_mirror_reports_synced_on_success(monkeypatch):
    _set_active_courses(monkeypatch, ["111"])
    monkeypatch.setattr(tools, "_enqueue_sync", lambda course_id: "plan-1")
    monkeypatch.setattr(tools, "_wait_for_plan",
                        lambda plan_id, **kwargs: {"state": "succeeded"})

    result = tools.refresh_mirror("111")
    assert result["ok"] is True
    assert result["status"] == "synced"


def test_refresh_mirror_reports_syncing_while_running(monkeypatch):
    _set_active_courses(monkeypatch, ["111"])
    monkeypatch.setattr(tools, "_enqueue_sync", lambda course_id: "plan-1")
    monkeypatch.setattr(tools, "_wait_for_plan",
                        lambda plan_id, **kwargs: {"state": "running"})

    result = tools.refresh_mirror("111")
    assert result["ok"] is True
    assert result["status"] == "syncing"


def test_refresh_mirror_reports_failure(monkeypatch):
    _set_active_courses(monkeypatch, ["111"])
    monkeypatch.setattr(tools, "_enqueue_sync", lambda course_id: "plan-1")
    monkeypatch.setattr(tools, "_wait_for_plan",
                        lambda plan_id, **kwargs: {"state": "failed"})

    result = tools.refresh_mirror("111")
    assert result["ok"] is False
    assert result["status"] == "failed"


def test_refresh_mirror_enqueue_value_error_maps_to_ok_false(monkeypatch):
    _set_active_courses(monkeypatch, ["111"])

    def _raise(course_id):
        raise ValueError("Not a Current course.")

    monkeypatch.setattr(tools, "_enqueue_sync", _raise)

    assert tools.refresh_mirror("111") == {"ok": False, "error": "Not a Current course."}


# --- server wiring -------------------------------------------------------------

def test_server_registers_exactly_the_six_read_only_tools():
    from api.mcp_server.server import mcp

    tool_names = set(mcp._tool_manager._tools.keys())
    assert tool_names == {
        "list_courses", "get_course_assignments", "get_roster",
        "get_submissions", "get_gradebook_snapshot", "refresh_mirror",
    }


def test_server_wrappers_return_compact_json(monkeypatch):
    from api.mcp_server import server

    monkeypatch.setattr(tools.config, "saved_courses", lambda: [
        {"id": "111", "name": "Algebra I", "nickname": "", "active": True},
    ])
    wire = server.list_courses()
    assert isinstance(wire, str)
    assert "\n" not in wire and ": " not in wire and ", " not in wire
    assert json.loads(wire) == tools.list_courses()
