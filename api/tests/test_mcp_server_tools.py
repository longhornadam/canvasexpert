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

from api import feedback_safety
from api.feedback_vault import Vault
from api.mcp_server import pseudonym, tools

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
    assert result["assignments"] == [{
        "id": 700010, "title": "Quiz 1", "description_text": "desc",
        "due_at": "2026-07-01T23:59:00Z", "points_possible": 10, "published": True,
    }]


def test_get_course_assignments_empty(monkeypatch):
    _set_active_courses(monkeypatch, ["111"])
    document = _catalog_document({}, [{"id": 1, "name": "Module 1", "position": 1, "items": []}])
    monkeypatch.setattr(tools, "read_catalog",
                        lambda course_id: {"catalog": document, "source": "canonical", "warnings": []})

    result = tools.get_course_assignments("111")
    assert result == {"ok": True, "course_id": "111", "course_name": "Test Course", "assignments": []}


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
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    monkeypatch.setattr(pseudonym, "_fetch_students", lambda course_id: (FIXTURE_USERS, None))
    monkeypatch.setattr(tools, "_fetch_sections", lambda course_id, canvas_get_all: SECTION_MAP)

    result = tools.get_roster("111")
    assert result["ok"] is True
    roster = result["roster"]
    assert len(roster) == 2
    pseudonyms = {row["pseudonym"] for row in roster}
    assert len(pseudonyms) == 2  # each student gets a distinct pseudonym
    section_sets = {tuple(row["section_names"]) for row in roster}
    assert section_sets == {("Period 1",), ("Period 2",)}
    assert roster == sorted(roster, key=lambda r: r["pseudonym"])  # sorted by pseudonym
    _assert_no_leaks(result)


def test_get_roster_empty(monkeypatch, tmp_path):
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    monkeypatch.setattr(pseudonym, "_fetch_students", lambda course_id: ([], None))
    monkeypatch.setattr(tools, "_fetch_sections", lambda course_id, canvas_get_all: {})

    assert tools.get_roster("111") == {"ok": True, "roster": []}


def test_get_roster_failure(monkeypatch, tmp_path):
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    monkeypatch.setattr(pseudonym, "_fetch_students", lambda course_id: (None, "Canvas fetch failed"))

    assert tools.get_roster("111") == {"ok": False, "error": "Canvas fetch failed"}


# --- get_submissions ----------------------------------------------------------

def test_get_submissions_happy_scrubs_real_name_and_short_name(monkeypatch, tmp_path):
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    monkeypatch.setattr(pseudonym, "_fetch_students", lambda course_id: (FIXTURE_USERS, None))
    monkeypatch.setattr(tools, "_assignment", lambda course_id, assignment_id: (
        {"id": 700010, "name": "Essay 1", "points_possible": 10, "due_at": "2026-07-01T23:59:00Z"}, None))
    monkeypatch.setattr(tools, "_assignment_submissions", lambda course_id, assignment_id: ([
        {"user_id": 900001, "workflow_state": "graded", "score": 9, "grade": "9",
         "submitted_at": "2026-07-01T20:00:00Z", "late": False, "missing": False,
         "excused": False,
         "body": "<p>Learner One and Lee worked together on this.</p>"},
    ], None))

    result = tools.get_submissions("111", "700010")
    assert result["ok"] is True
    assert result["assignment"] == {
        "id": 700010, "title": "Essay 1", "points_possible": 10, "due_at": "2026-07-01T23:59:00Z",
    }
    subs = result["submissions"]
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


def test_get_submissions_empty(monkeypatch, tmp_path):
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    monkeypatch.setattr(pseudonym, "_fetch_students", lambda course_id: (FIXTURE_USERS, None))
    monkeypatch.setattr(tools, "_assignment", lambda course_id, assignment_id: (
        {"id": 700010, "name": "Essay 1", "points_possible": 10, "due_at": ""}, None))
    monkeypatch.setattr(tools, "_assignment_submissions", lambda course_id, assignment_id: ([], None))

    result = tools.get_submissions("111", "700010")
    assert result["ok"] is True
    assert result["submissions"] == []


def test_get_submissions_failure(monkeypatch, tmp_path):
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    monkeypatch.setattr(pseudonym, "_fetch_students", lambda course_id: (FIXTURE_USERS, None))
    monkeypatch.setattr(tools, "_assignment", lambda course_id, assignment_id: (None, "Assignment not found"))

    assert tools.get_submissions("111", "700010") == {"ok": False, "error": "Assignment not found"}


def test_get_submissions_rejects_non_current_course(monkeypatch, tmp_path):
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["222"])
    result = tools.get_submissions("111", "700010")
    assert result["ok"] is False
    assert "not a Current course" in result["error"]


# --- get_gradebook_snapshot ---------------------------------------------------

def test_get_gradebook_snapshot_happy(monkeypatch, tmp_path):
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    monkeypatch.setattr(tools, "_course_students", lambda course_id: (GRADEBOOK_STUDENTS, None))
    monkeypatch.setattr(tools, "_course_assignments", lambda course_id: (GRADEBOOK_ASSIGNMENTS, None))
    monkeypatch.setattr(tools, "_course_submissions", lambda course_id: (GRADEBOOK_SUBS, None))

    result = tools.get_gradebook_snapshot("111")
    assert result["ok"] is True
    assert result["class_avg"] == 90.0
    assert result["student_count"] == 2
    assert result["assignments"] == [{
        "id": "700010", "title": "Quiz 1", "due_at": "2026-07-01",
        "points": 10, "submitted": 2, "graded": 1, "missing": 0, "late": 0, "avg_pct": 90,
    }]
    students = result["students"]
    assert len(students) == 2
    for s in students:
        assert set(s.keys()) == {"pseudonym", "missing", "late", "ungraded", "pct"}
    _assert_no_leaks(result)


def test_get_gradebook_snapshot_empty(monkeypatch, tmp_path):
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    monkeypatch.setattr(tools, "_course_students", lambda course_id: ([], None))
    monkeypatch.setattr(tools, "_course_assignments", lambda course_id: ([], None))
    monkeypatch.setattr(tools, "_course_submissions", lambda course_id: ([], None))

    result = tools.get_gradebook_snapshot("111")
    assert result["ok"] is True
    assert result["class_avg"] is None
    assert result["student_count"] == 0
    assert result["assignments"] == []
    assert result["students"] == []


def test_get_gradebook_snapshot_failure(monkeypatch, tmp_path):
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    monkeypatch.setattr(tools, "_course_students", lambda course_id: (None, "Canvas fetch failed"))

    assert tools.get_gradebook_snapshot("111") == {"ok": False, "error": "Canvas fetch failed"}


def test_get_gradebook_snapshot_rejects_non_current_course(monkeypatch, tmp_path):
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["222"])
    result = tools.get_gradebook_snapshot("111")
    assert result["ok"] is False
    assert "not a Current course" in result["error"]


# --- pseudonym round trip -----------------------------------------------------

def test_pseudonym_reverse_round_trip(monkeypatch, tmp_path):
    vault_path = _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    monkeypatch.setattr(pseudonym, "_fetch_students", lambda course_id: (FIXTURE_USERS, None))
    monkeypatch.setattr(tools, "_fetch_sections", lambda course_id, canvas_get_all: SECTION_MAP)

    result = tools.get_roster("111")
    assert result["ok"] is True
    pseudonym_value = result["roster"][0]["pseudonym"]

    fresh_vault = Vault(vault_path)  # re-open from disk, not the in-memory instance
    reversed_entry = fresh_vault.reverse(pseudonym_value)
    assert reversed_entry is not None
    assert reversed_entry["real_name"] in {"Learner One", "Learner Two"}
    assert reversed_entry["canvas_id"] in {"900001", "900002"}


# --- no-PII sweep + scan_payload green ---------------------------------------

def test_no_pii_sweep_and_scan_payload_green(monkeypatch, tmp_path):
    vault_path = _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    monkeypatch.setattr(tools, "_course_students", lambda course_id: (GRADEBOOK_STUDENTS, None))
    monkeypatch.setattr(tools, "_course_assignments", lambda course_id: (GRADEBOOK_ASSIGNMENTS, None))
    monkeypatch.setattr(tools, "_course_submissions", lambda course_id: (GRADEBOOK_SUBS, None))

    result = tools.get_gradebook_snapshot("111")
    assert result["ok"] is True
    _assert_no_leaks(result)

    fresh_vault = Vault(vault_path)
    verdict = feedback_safety.scan_payload(result, fresh_vault)
    assert verdict["green"] is True
    assert verdict["hard"] == []


def test_no_pii_sweep_scan_payload_green_for_submissions(monkeypatch, tmp_path):
    vault_path = _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    monkeypatch.setattr(pseudonym, "_fetch_students", lambda course_id: (FIXTURE_USERS, None))
    monkeypatch.setattr(tools, "_assignment", lambda course_id, assignment_id: (
        {"id": 700010, "name": "Essay 1", "points_possible": 10, "due_at": "2026-07-01T23:59:00Z"}, None))
    monkeypatch.setattr(tools, "_assignment_submissions", lambda course_id, assignment_id: ([
        {"user_id": 900001, "workflow_state": "graded", "score": 9, "grade": "9",
         "submitted_at": "2026-07-01T20:00:00Z", "late": False, "missing": False,
         "excused": False,
         "body": "<p>Learner One and Lee worked together on this.</p>"},
    ], None))

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


# --- server wiring -------------------------------------------------------------

def test_server_registers_exactly_the_five_read_only_tools():
    from api.mcp_server.server import mcp

    tool_names = set(mcp._tool_manager._tools.keys())
    assert tool_names == {
        "list_courses", "get_course_assignments", "get_roster",
        "get_submissions", "get_gradebook_snapshot",
    }
