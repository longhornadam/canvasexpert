"""Offline tests: Work Registry discovery providers read the CanvasMirror.

Fixture style mirrors ``api/tests/test_mirror_queries.py``: workspace root is
redirected to ``tmp_path`` and the mirror is populated with ``store.write_*``
writers + ``store.record_pass(course_id, "full", ok=True)``. ``store.now_iso()``
marks a pass fresh; a pinned old ISO string marks it stale.
"""
from __future__ import annotations

import time

from api.mirror import store
from api.webui import workspace
from api.work_registry.providers import call_canvas_get_all
from api.work_registry.providers import grading_debt, home_attention, late_work, roster_warnings

COURSE = "555001"

ASSIGNMENTS = [
    {"id": 700100, "name": "Essay", "due_at": "2026-07-01T09:00:00Z",
     "points_possible": 10, "published": True, "html_url": "u",
     "submission_types": ["online_text_entry"]},
    {"id": 700101, "name": "Reflection", "due_at": "2026-07-05T09:00:00Z",
     "points_possible": 10, "published": True, "html_url": "u",
     "submission_types": ["online_text_entry"]},
]
USERS = [
    {"id": 900101, "name": "Learner One", "sortable_name": "One, Learner",
     "short_name": "Lee", "sis_user_id": "SIS-900101", "enrollments": []},
    {"id": 900102, "name": "Learner Two", "sortable_name": "Two, Learner",
     "short_name": "Learner Two", "sis_user_id": "SIS-900102", "enrollments": []},
]

# Assignment 700100: one on-time ungraded submission (grading debt candidate,
# no comments) and two genuinely late submissions with string ids (aggregation
# check). Assignment 700101: a submission carrying submission_comments in the
# exact slice-5 mirror shape ({author_id, comment, created_at}) so
# grading_debt._teacher_touched and home_attention's comment classifier are
# both exercised against mirror rows, not live Canvas rows.
SUBMISSIONS_700100 = [
    {"assignment_id": 700100, "user_id": 900101, "workflow_state": "submitted",
     "submitted_at": "2026-07-02T09:00:00Z", "score": None,
     "submission_comments": []},
    {"assignment_id": 700100, "user_id": "900103", "workflow_state": "late",
     "late": True, "submitted_at": "2026-07-05T09:00:00Z", "score": 7,
     "submission_comments": []},
    {"assignment_id": 700100, "user_id": "900104", "workflow_state": "late",
     "late": True, "submitted_at": "2026-07-06T09:00:00Z", "score": 8,
     "submission_comments": []},
]
SUBMISSIONS_700101 = [
    {"assignment_id": 700101, "user_id": 900102, "workflow_state": "submitted",
     "submitted_at": "2026-07-06T10:30:00Z", "score": None,
     "submission_comments": [
         {"author_id": "900201", "comment": "Please revise your intro.",
          "created_at": "2026-07-06T09:00:00Z"},
         {"author_id": "900102", "comment": "Updated, thanks!",
          "created_at": "2026-07-06T10:00:00Z"},
     ]},
]


def _populate(root, *, fresh=True):
    stamp = store.now_iso() if fresh else "2026-01-01T00:00:00Z"
    store.write_roster(COURSE, USERS, {}, root=root, attempted_at=stamp)
    store.write_assignments(COURSE, ASSIGNMENTS, root=root, attempted_at=stamp)
    store.merge_submissions(COURSE, "700100", SUBMISSIONS_700100, root=root,
                            attempted_at=stamp, replace=True)
    store.merge_submissions(COURSE, "700101", SUBMISSIONS_700101, root=root,
                            attempted_at=stamp, replace=True)
    for pass_name in ("full", "roster"):
        store.record_pass(COURSE, pass_name, ok=True, attempted_at=stamp, root=root)


def _explode(*_args, **_kwargs):
    raise AssertionError("live Canvas read attempted")


def _mount(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))


# --- the shared wrapper itself --------------------------------------------------

def test_wrapper_serves_fresh_mirror_for_all_three_shapes_with_zero_live_calls(monkeypatch, tmp_path):
    _mount(monkeypatch, tmp_path)
    _populate(str(tmp_path))
    deadline = time.monotonic() + 5

    assignments = call_canvas_get_all(
        _explode, f"/api/v1/courses/{COURSE}/assignments", {"per_page": 100}, deadline)
    assert {a["id"] for a in assignments} == {"700100", "700101"}

    users = call_canvas_get_all(
        _explode, f"/api/v1/courses/{COURSE}/users",
        {"enrollment_type[]": "student", "include[]": "enrollments", "per_page": 100}, deadline)
    assert {u["id"] for u in users} == {"900101", "900102"}

    submissions = call_canvas_get_all(
        _explode, f"/api/v1/courses/{COURSE}/students/submissions",
        {"student_ids[]": "all", "per_page": 100}, deadline)
    assert {s["assignment_id"] for s in submissions} == {"700100", "700101"}
    # str-id rows: user ids stored either as int or str at write time both
    # come back as strings from the mirror.
    assert {s["user_id"] for s in submissions} == {"900101", "900102", "900103", "900104"}


def test_wrapper_falls_back_live_when_mirror_is_stale(monkeypatch, tmp_path):
    _mount(monkeypatch, tmp_path)
    _populate(str(tmp_path), fresh=False)
    deadline = time.monotonic() + 5
    live_rows = [{"id": 1, "name": "Live Assignment"}]

    def fake_get(path, params=None, timeout=None, deadline=None):
        return live_rows, None

    result = call_canvas_get_all(
        fake_get, f"/api/v1/courses/{COURSE}/assignments", {"per_page": 100}, deadline)
    assert result == live_rows


def test_wrapper_never_consults_mirror_for_a_non_matching_path(monkeypatch, tmp_path):
    _mount(monkeypatch, tmp_path)
    _populate(str(tmp_path))  # fresh mirror present, but path isn't one of the 3 shapes
    deadline = time.monotonic() + 5
    calls = []

    def fake_get(path, params=None, timeout=None, deadline=None):
        calls.append(path)
        return [], None

    call_canvas_get_all(
        fake_get, f"/api/v1/courses/{COURSE}/group_categories", {"per_page": 50}, deadline)
    assert calls == [f"/api/v1/courses/{COURSE}/group_categories"]


def test_wrapper_falls_back_live_when_mirror_read_errors(monkeypatch, tmp_path):
    _mount(monkeypatch, tmp_path)
    _populate(str(tmp_path))
    from api.work_registry.providers import mirror_queries
    monkeypatch.setattr(mirror_queries, "course_assignments", lambda course_id: (None, "boom"))
    deadline = time.monotonic() + 5
    live_rows = [{"id": 1}]

    def fake_get(path, params=None, timeout=None, deadline=None):
        return live_rows, None

    result = call_canvas_get_all(
        fake_get, f"/api/v1/courses/{COURSE}/assignments", {"per_page": 100}, deadline)
    assert result == live_rows


# --- providers, end to end -------------------------------------------------------

def test_late_work_scan_course_reads_mirror_with_zero_live_calls(monkeypatch, tmp_path):
    _mount(monkeypatch, tmp_path)
    _populate(str(tmp_path))
    monkeypatch.setattr(late_work.config, "get_sweep_settings",
                        lambda: {"skip_weekends": False, "holidays": []})
    monkeypatch.setattr(late_work.config, "get_extra_time", lambda course_id: [])

    findings = late_work.scan_course(
        COURSE, now="2026-07-11T12:00:00+00:00", deadline=time.monotonic() + 5,
        canvas_get_all=_explode,
    )
    assert len(findings) == 1
    assert findings[0]["kind"] == "late.work"
    assert findings[0]["assignment_id"] == "700100"
    # Two late, string-id submissions aggregate onto the one assignment.
    assert findings[0]["counts"] == {"total": 2, "pending": 2, "affected": 2}


def test_grading_debt_and_home_attention_read_mirror_with_comment_shape(monkeypatch, tmp_path):
    _mount(monkeypatch, tmp_path)
    _populate(str(tmp_path))
    monkeypatch.setattr(grading_debt, "powergrader_evidence", lambda: {})

    debt_findings = grading_debt.scan_course(
        COURSE, now="2026-07-11T12:00:00+00:00", deadline=time.monotonic() + 5,
        canvas_get_all=_explode,
    )
    # Assignment 700100/user 900101: submitted, no score, no comments -> debt.
    # Assignment 700101/user 900102: no score but a staff comment -> touched,
    # so not counted as debt (exercises submission_comments from the mirror).
    debt_by_assignment = {item["assignment_id"]: item["counts"] for item in debt_findings}
    assert debt_by_assignment == {"700100": {"total": 1, "pending": 1, "affected": 1}}

    followups = home_attention.scan_comment_follow_up(
        COURSE, now="2026-07-11T12:00:00+00:00", deadline=time.monotonic() + 5,
        canvas_get_all=_explode,
    )
    definite = [item for item in followups if item["kind"] == "grade.followup"]
    assert len(definite) == 1
    assert definite[0]["assignment_id"] == "700101"
    assert definite[0]["counts"] == {"total": 1, "pending": 1, "affected": 1}

    ready = home_attention.scan_powergrader_ready(
        COURSE, now="2026-07-11T12:00:00+00:00", deadline=time.monotonic() + 5,
        canvas_get_all=_explode,
    )
    ready_ids = {item["assignment_id"] for item in ready}
    assert ready_ids == {"700100", "700101"}


def test_grading_debt_falls_back_live_when_mirror_is_stale(monkeypatch, tmp_path):
    _mount(monkeypatch, tmp_path)
    _populate(str(tmp_path), fresh=False)
    monkeypatch.setattr(grading_debt, "powergrader_evidence", lambda: {})

    def fake_get(path, params=None, timeout=None, deadline=None):
        if path.endswith("/assignments"):
            return [{"id": "live-1", "due_at": "2026-07-10T11:00:00+00:00"}], None
        return [
            {"assignment_id": "live-1", "user_id": "live-user", "workflow_state": "submitted",
             "submitted_at": "2026-07-11T11:00:00+00:00", "score": None, "submission_comments": []},
        ], None

    findings = grading_debt.scan_course(
        COURSE, now="2026-07-11T12:00:00+00:00", deadline=time.monotonic() + 5,
        canvas_get_all=fake_get,
    )
    assert len(findings) == 1
    assert findings[0]["assignment_id"] == "live-1"


def test_roster_warnings_reads_users_from_mirror_groups_stay_live(monkeypatch, tmp_path):
    _mount(monkeypatch, tmp_path)
    _populate(str(tmp_path))
    monkeypatch.setattr(roster_warnings.config, "get_roster_group_scheme",
                        lambda course_id: {"selected_group_category_id": "cat-1"})
    monkeypatch.setattr(roster_warnings.config, "get_extra_time",
                        lambda course_id: [{"id": "900101", "days": 0}])
    monkeypatch.setattr(roster_warnings, "_vault_context",
                        lambda: ({}, set(), {"literary": [], "dup_first": [], "common_word": []}))

    def fake_get(path, params=None, timeout=None, deadline=None):
        if path.endswith("/users"):
            raise AssertionError("live users read attempted; mirror should have served it")
        return [], None  # group_categories / groups / memberships stay live and empty

    findings = roster_warnings.scan_course(
        COURSE, now="2026-07-11T12:00:00+00:00", deadline=time.monotonic() + 5,
        canvas_get_all=fake_get,
    )
    assert {item["kind"] for item in findings} == {"roster.warning"}
    # Both mirrored students get missing_pseudonym + group_unset;
    # only "900101" also gets extra_time_without_days.
    assert sum(item["counts"]["affected"] for item in findings) == 5


def test_roster_warnings_uses_fresh_group_snapshot_without_live_group_calls(monkeypatch, tmp_path):
    _mount(monkeypatch, tmp_path)
    _populate(str(tmp_path))
    store.write_groups(COURSE, [{
        "category_id": "cat-1",
        "category_name": "Teams",
        "groups": [{
            "id": "group-1",
            "name": "Team 1",
            "memberships": [{"id": "membership-1", "user_id": "900101"}],
        }],
    }])
    monkeypatch.setattr(roster_warnings.config, "get_roster_group_scheme",
                        lambda course_id: {"selected_group_category_id": "cat-1"})
    monkeypatch.setattr(roster_warnings.config, "get_extra_time", lambda course_id: [])
    monkeypatch.setattr(roster_warnings, "_vault_context",
                        lambda: ({}, set(), {"literary": [], "dup_first": [], "common_word": []}))

    findings = roster_warnings.scan_course(
        COURSE, now="2026-07-11T12:00:00+00:00", deadline=time.monotonic() + 5,
        canvas_get_all=_explode,
    )

    assert sorted(item["counts"]["affected"] for item in findings) == [1, 2]
    assert all("user_id" not in item and "name" not in item for item in findings)
