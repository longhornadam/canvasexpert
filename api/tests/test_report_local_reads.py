"""Coverage for the 1.0beta-06b shared-helper refactor of `api/report_local_reads.py`:
the new `local_course_submissions_by_user` (grouped, for
`api/portfolio_service.py::build_merged_portfolios`) and confirmation that the
refactor sharing `_joined_course_records` between it and the existing
`local_course_submissions` did not change the latter's behavior.

`local_course_submissions`'s own existing behavior for its existing caller
(`build_packet`) is covered by `api/tests/test_student_packet.py`, which this
brief does not modify at all — see that file's own suite in the named
acceptance gate for proof the refactor left it byte-for-byte unchanged.
"""
from __future__ import annotations

import pytest

from api import report_local_reads
from api.mirror import store
from api.webui import workspace

COURSE_ID = "222"
ASSIGNMENT_ID = "700020"
STAMP = "2026-07-18T12:00:00Z"


@pytest.fixture(autouse=True)
def _workspace(monkeypatch, tmp_path):
    # report_local_reads never takes a root= — it always resolves through the
    # configured workspace, so tests redirect it here.
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    return tmp_path


def _seed_current_course(rows, *, assignment_id=ASSIGNMENT_ID):
    store.write_assignments(COURSE_ID, [{
        "id": assignment_id, "name": "Essay 1", "due_at": "2026-07-01T23:59:00Z",
        "points_possible": 10, "published": True,
        "submission_types": ["online_text_entry"],
    }], attempted_at=STAMP)
    store.merge_submissions(COURSE_ID, assignment_id, rows, attempted_at=STAMP, replace=True)
    store.record_pass(COURSE_ID, "full", ok=True, attempted_at=STAMP)


# --- (a) grouped result matches per-student local_course_submissions ---------------

def test_local_course_submissions_by_user_groups_same_records_per_student():
    rows = [
        {"assignment_id": ASSIGNMENT_ID, "user_id": "900001", "workflow_state": "submitted",
         "submitted_at": STAMP, "score": 9, "submission_type": "online_text_entry", "body": "A"},
        {"assignment_id": ASSIGNMENT_ID, "user_id": "900002", "workflow_state": "submitted",
         "submitted_at": STAMP, "score": 7, "submission_type": "online_upload", "body": ""},
    ]
    _seed_current_course(rows)

    grouped = report_local_reads.local_course_submissions_by_user(COURSE_ID)
    assert grouped is not None
    assert set(grouped.keys()) == {"900001", "900002"}
    for uid in ("900001", "900002"):
        assert grouped[uid] == report_local_reads.local_course_submissions(COURSE_ID, uid)


def test_local_course_submissions_by_user_current_but_empty_course_returns_empty_dict():
    store.write_assignments(COURSE_ID, [], attempted_at=STAMP)
    store.record_pass(COURSE_ID, "full", ok=True, attempted_at=STAMP)
    assert report_local_reads.local_course_submissions_by_user(COURSE_ID) == {}


def test_local_course_submissions_by_user_excludes_submissions_without_a_matching_assignment():
    # A submission whose assignment isn't in the local assignment set at all
    # must be excluded from the joined/grouped result, exactly like the
    # single-student function's existing "assignment is None -> skip" gate.
    store.write_assignments(COURSE_ID, [{
        "id": ASSIGNMENT_ID, "name": "Essay 1", "due_at": "", "points_possible": 10,
        "published": True, "submission_types": ["online_text_entry"],
    }], attempted_at=STAMP)
    store.merge_submissions(COURSE_ID, "999999", [{
        "assignment_id": "999999", "user_id": "900003", "workflow_state": "submitted",
        "submitted_at": STAMP, "score": 5, "submission_type": "online_text_entry",
    }], attempted_at=STAMP, replace=True)
    store.record_pass(COURSE_ID, "full", ok=True, attempted_at=STAMP)

    assert report_local_reads.local_course_submissions_by_user(COURSE_ID) == {}


# --- not-current gate is identical for both public functions -----------------------

def test_local_course_submissions_by_user_returns_none_when_submissions_pass_never_recorded():
    store.write_assignments(COURSE_ID, [{
        "id": ASSIGNMENT_ID, "name": "Essay 1", "due_at": "", "points_possible": 10,
        "published": True, "submission_types": ["online_text_entry"],
    }], attempted_at=STAMP)
    store.merge_submissions(COURSE_ID, ASSIGNMENT_ID, [{
        "assignment_id": ASSIGNMENT_ID, "user_id": "900001", "workflow_state": "submitted",
        "submitted_at": STAMP, "score": 9, "submission_type": "online_text_entry",
    }], attempted_at=STAMP, replace=True)
    # No record_pass -> private_submissions reports state "unavailable", not "current".
    assert report_local_reads.local_course_submissions_by_user(COURSE_ID) is None
    assert report_local_reads.local_course_submissions(COURSE_ID, "900001") is None


def test_local_course_submissions_by_user_returns_none_when_no_local_document_exists():
    assert report_local_reads.local_course_submissions_by_user(COURSE_ID) is None
    assert report_local_reads.local_course_submissions(COURSE_ID, "900001") is None


# --- refactor proof: both public functions share one underlying join pass ----------

def test_both_public_functions_delegate_to_the_one_shared_join_pass(monkeypatch):
    rows = [
        {"assignment_id": ASSIGNMENT_ID, "user_id": "900001", "workflow_state": "submitted",
         "submitted_at": STAMP, "score": 9, "submission_type": "online_text_entry", "body": "A"},
    ]
    _seed_current_course(rows)

    calls = []
    original = report_local_reads._joined_course_records

    def _spy(course_id, *, root=None):
        calls.append(course_id)
        return original(course_id, root=root)

    monkeypatch.setattr(report_local_reads, "_joined_course_records", _spy)

    report_local_reads.local_course_submissions(COURSE_ID, "900001")
    report_local_reads.local_course_submissions_by_user(COURSE_ID)

    assert calls == [COURSE_ID, COURSE_ID]
