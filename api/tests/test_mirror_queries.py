"""Offline tests for mirror-backed reads: the queries provider, the
mirror-first snapshot loader, and the MCP tools' mirror paths.

Freshness uses real store timestamps (now_iso) so "fresh" means fresh; stale
cases pin old attempted_at stamps.
"""
from __future__ import annotations

import json

from api import gradebook_queries, gradebook_snapshot
from api.feedback_vault import Vault
from api.mirror import queries, store
from api.mcp_server import tools
from api.webui import workspace

COURSE = "111"

USERS = [
    {"id": 900001, "name": "Learner One", "sortable_name": "One, Learner",
     "short_name": "Lee", "sis_user_id": "SIS-900001",
     "enrollments": [{"course_section_id": 800001}]},
    {"id": 900002, "name": "Learner Two", "sortable_name": "Two, Learner",
     "short_name": "Learner Two", "sis_user_id": "SIS-900002",
     "enrollments": [{"course_section_id": 800002}]},
]
SECTIONS = {"800001": "Period 1", "800002": "Period 2"}
ASSIGNMENTS = [
    {"id": 700010, "name": "Essay 1", "due_at": "2026-07-01T23:59:00Z",
     "points_possible": 10, "published": True, "html_url": "u"},
]
SUBMISSIONS = [
    {"assignment_id": 700010, "user_id": 900001, "workflow_state": "graded",
     "submitted_at": "2026-07-01T20:00:00Z", "graded_at": "2026-07-02T09:00:00Z",
     "score": 9, "grade": "9", "late": False, "missing": False, "excused": False,
     "attempt": 1, "grade_matches_current_submission": True,
     "submission_type": "online_text_entry",
     "body": "<p>Learner One and Lee wrote this.</p>"},
    {"assignment_id": 700010, "user_id": 900002, "workflow_state": "unsubmitted",
     "submitted_at": None, "graded_at": None, "score": None, "grade": None,
     "late": False, "missing": True, "excused": False, "attempt": None,
     "grade_matches_current_submission": None, "submission_type": "", "body": ""},
]


def _populate(root, *, fresh=True):
    stamp = store.now_iso() if fresh else "2026-01-01T00:00:00Z"
    store.write_roster(COURSE, USERS, SECTIONS, root=root, attempted_at=stamp)
    store.write_assignments(COURSE, ASSIGNMENTS, root=root, attempted_at=stamp)
    store.merge_submissions(COURSE, "700010", SUBMISSIONS, root=root,
                            attempted_at=stamp, replace=True)
    for pass_name in ("full", "roster"):
        store.record_pass(COURSE, pass_name, ok=True, attempted_at=stamp, root=root)


def _raise_if_live(monkeypatch):
    def _explode(*_args, **_kwargs):
        raise AssertionError("live Canvas read attempted")
    for name in ("course_students", "course_assignments", "course_submissions",
                 "assignment", "assignment_submissions"):
        monkeypatch.setattr(gradebook_queries, name, _explode)


# --- queries provider ----------------------------------------------------------

def test_queries_interface_serves_canvas_shaped_rows(tmp_path):
    _populate(str(tmp_path))
    students, err = queries.course_students(COURSE, root=str(tmp_path))
    assert err is None and {s["id"] for s in students} == {"900001", "900002"}
    assignments, err = queries.course_assignments(COURSE, root=str(tmp_path))
    assert err is None and assignments[0]["name"] == "Essay 1"
    subs, err = queries.course_submissions(COURSE, root=str(tmp_path))
    assert err is None and len(subs) == 2
    row, err = queries.assignment(COURSE, "700010", root=str(tmp_path))
    assert err is None and row["points_possible"] == 10
    rows, err = queries.assignment_submissions(COURSE, "700010", root=str(tmp_path))
    assert err is None and rows[0]["user_id"] == "900001"


def test_queries_report_unavailable_for_unknown_course(tmp_path):
    for fn in (lambda: queries.course_students("999", root=str(tmp_path)),
               lambda: queries.assignment("999", "1", root=str(tmp_path))):
        data, err = fn()
        assert data is None and err == queries.MIRROR_UNAVAILABLE


def test_freshness_gates_on_serve_max_age(tmp_path):
    _populate(str(tmp_path), fresh=False)
    assert queries.data_freshness(COURSE, root=str(tmp_path)) == ""
    _populate(str(tmp_path), fresh=True)
    assert queries.data_freshness(COURSE, root=str(tmp_path)) != ""


def test_snapshot_queries_requires_fresh_and_complete_mirror(tmp_path):
    namespace, synced = queries.snapshot_queries(COURSE, root=str(tmp_path))
    assert namespace is None and synced == ""
    _populate(str(tmp_path))
    namespace, synced = queries.snapshot_queries(COURSE, root=str(tmp_path))
    assert namespace is not None and synced != ""


# --- mirror-first shared snapshot loader --------------------------------------------

def test_load_snapshot_prefers_fresh_mirror(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    _populate(str(tmp_path))
    _raise_if_live(monkeypatch)  # would explode if the live path were taken
    snapshot, error = gradebook_snapshot.load_snapshot(COURSE)
    assert error is None
    assert snapshot["source"] == "mirror"
    assert snapshot["synced_at"] != ""
    assert snapshot["student_count"] == 2
    assert snapshot["total_missing"] == 1
    assert snapshot["assignments"][0]["name"] == "Essay 1"


def test_load_snapshot_falls_back_to_live_when_stale(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    _populate(str(tmp_path), fresh=False)
    monkeypatch.setattr(gradebook_queries, "course_students", lambda cid: ([], None))
    monkeypatch.setattr(gradebook_queries, "course_assignments", lambda cid: ([], None))
    monkeypatch.setattr(gradebook_queries, "course_submissions", lambda cid: ([], None))
    snapshot, error = gradebook_snapshot.load_snapshot(COURSE)
    assert error is None
    assert snapshot["source"] == "canvas"
    assert snapshot["synced_at"] == ""


def test_load_snapshot_explicit_queries_override_skips_mirror(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    _populate(str(tmp_path))
    from types import SimpleNamespace
    override = SimpleNamespace(course_students=lambda cid: ([], None),
                               course_assignments=lambda cid: ([], None),
                               course_submissions=lambda cid: ([], None))
    snapshot, _ = gradebook_snapshot.load_snapshot(COURSE, queries=override)
    assert snapshot["source"] == "canvas"
    assert snapshot["student_count"] == 0


# --- MCP tools: mirror paths ------------------------------------------------------

def _mcp_setup(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    monkeypatch.setattr(tools.config, "active_courses", lambda: [{"id": COURSE}])
    monkeypatch.setattr(tools, "_vault_factory",
                        lambda: Vault(str(tmp_path / "vault.json")))


def test_mcp_get_roster_serves_from_mirror_without_canvas(monkeypatch, tmp_path):
    _mcp_setup(monkeypatch, tmp_path)
    _populate(str(tmp_path))
    result = tools.get_roster(COURSE)
    assert result["ok"] is True
    assert result["source"] == "mirror"
    assert result["synced_at"] != ""
    assert len(result["roster"]["rows"]) == 2
    dumped = json.dumps(result)
    for leak in ("Learner One", "900001", "SIS-900001"):
        assert leak not in dumped


def test_mcp_get_submissions_serves_from_mirror_scrubbed(monkeypatch, tmp_path):
    _mcp_setup(monkeypatch, tmp_path)
    _populate(str(tmp_path))
    result = tools.get_submissions(COURSE, "700010")
    assert result["ok"] is True
    assert result["source"] == "mirror"
    assert result["assignment"]["title"] == "Essay 1"
    rows = [dict(zip(result["submissions"]["columns"], row))
            for row in result["submissions"]["rows"]]
    graded = next(r for r in rows if r["workflow_state"] == "graded")
    # Real name and nickname scrubbed to the same pseudonym.
    assert graded["pseudonym"] in graded["text"]
    dumped = json.dumps(result)
    for leak in ("Learner One", "Lee", "900001"):
        assert leak not in dumped


def test_mcp_get_gradebook_snapshot_serves_from_mirror(monkeypatch, tmp_path):
    _mcp_setup(monkeypatch, tmp_path)
    _populate(str(tmp_path))
    result = tools.get_gradebook_snapshot(COURSE)
    assert result["ok"] is True
    assert result["source"] == "mirror"
    assert result["synced_at"] != ""
    assert len(result["students"]["rows"]) == 2


def test_mcp_stale_mirror_is_not_served(monkeypatch, tmp_path):
    _mcp_setup(monkeypatch, tmp_path)
    _populate(str(tmp_path), fresh=False)
    assert tools._mirror_roster_doc(COURSE) is None
    assert tools._mirror_submission_bundle(COURSE, "700010") is None


def test_mcp_seamed_tests_bypass_the_mirror(monkeypatch, tmp_path):
    _mcp_setup(monkeypatch, tmp_path)
    _populate(str(tmp_path))
    from api.mcp_server import pseudonym
    monkeypatch.setattr(pseudonym, "_fetch_students",
                        lambda course_id: (USERS, None))
    assert tools._mirror_roster_doc(COURSE) is None  # seam guard wins
