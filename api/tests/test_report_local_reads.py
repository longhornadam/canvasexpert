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

import json

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


# --- 1.0beta-06d: local_course_freshness -------------------------------------------

def test_local_course_freshness_reports_mirror_with_min_synced_at_when_current():
    # Assignments and submissions become "current" via two independent stamps
    # (write_assignments' attempted_at vs. record_pass' attempted_at) — the
    # earlier of the two must win, proving this reads both envelopes
    # independently rather than reusing one shared timestamp.
    stamp_assignments = "2026-07-10T08:00:00Z"
    stamp_submissions = "2026-07-15T09:00:00Z"
    store.write_assignments(COURSE_ID, [{
        "id": ASSIGNMENT_ID, "name": "Essay 1", "due_at": "", "points_possible": 10,
        "published": True, "submission_types": ["online_text_entry"],
    }], attempted_at=stamp_assignments)
    store.merge_submissions(COURSE_ID, ASSIGNMENT_ID, [{
        "assignment_id": ASSIGNMENT_ID, "user_id": "900001", "workflow_state": "submitted",
        "submitted_at": stamp_submissions, "score": 9, "submission_type": "online_text_entry",
    }], attempted_at=stamp_submissions, replace=True)
    store.record_pass(COURSE_ID, "full", ok=True, attempted_at=stamp_submissions)

    assert report_local_reads.local_course_freshness(COURSE_ID) == {
        "source": "mirror", "synced_at": stamp_assignments,
    }


def test_local_course_freshness_reports_canvas_when_no_local_document_exists():
    assert report_local_reads.local_course_freshness(COURSE_ID) == {
        "source": "canvas", "synced_at": "",
    }


def test_local_course_freshness_reports_canvas_when_submissions_pass_never_recorded():
    # Same not-current gate as local_course_submissions/_by_user: assignments
    # exist, but no "full"/"delta" pass was ever recorded for submissions.
    store.write_assignments(COURSE_ID, [{
        "id": ASSIGNMENT_ID, "name": "Essay 1", "due_at": "", "points_possible": 10,
        "published": True, "submission_types": ["online_text_entry"],
    }], attempted_at=STAMP)
    assert report_local_reads.local_course_submissions_by_user(COURSE_ID) is None
    assert report_local_reads.local_course_freshness(COURSE_ID) == {
        "source": "canvas", "synced_at": "",
    }


def test_local_course_freshness_does_not_change_when_joined_records_would_fail():
    # A submission whose assignment isn't in the local set at all still leaves
    # both envelopes "current" -- local_course_freshness reads envelope state
    # only, never the join, so it must still report "mirror" here even though
    # `_joined_course_records` would drop that one submission.
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
    assert report_local_reads.local_course_freshness(COURSE_ID) == {
        "source": "mirror", "synced_at": STAMP,
    }


# --- 1.0beta-06d: write_source_manifest --------------------------------------------

def test_write_source_manifest_merges_by_course_id_leaving_other_courses_untouched(tmp_path):
    dest = tmp_path / "student_folder"
    dest.mkdir()
    report_local_reads.write_source_manifest(str(dest), {
        "111": {"course_name": "Course One", "source": "mirror",
                "synced_at": STAMP, "generated_at": STAMP},
    })
    report_local_reads.write_source_manifest(str(dest), {
        "222": {"course_name": "Course Two", "source": "canvas",
                "synced_at": "", "generated_at": STAMP},
    })

    with open(dest / "_source_manifest.json", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["111"] == {"course_name": "Course One", "source": "mirror",
                              "synced_at": STAMP, "generated_at": STAMP}
    assert manifest["222"] == {"course_name": "Course Two", "source": "canvas",
                              "synced_at": "", "generated_at": STAMP}

    # Re-running for course "111" only updates that one entry.
    later = "2026-07-19T00:00:00Z"
    report_local_reads.write_source_manifest(str(dest), {
        "111": {"course_name": "Course One", "source": "mirror",
                "synced_at": later, "generated_at": later},
    })
    with open(dest / "_source_manifest.json", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["111"]["synced_at"] == later
    assert manifest["222"]["synced_at"] == ""  # untouched by the re-run


def test_write_source_manifest_tolerates_a_missing_or_corrupt_existing_file(tmp_path):
    dest = tmp_path / "student_folder"
    dest.mkdir()
    manifest_path = dest / "_source_manifest.json"
    manifest_path.write_text("{not valid json", encoding="utf-8")

    report_local_reads.write_source_manifest(str(dest), {
        "111": {"course_name": "Course One", "source": "mirror",
                "synced_at": STAMP, "generated_at": STAMP},
    })

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest == {"111": {"course_name": "Course One", "source": "mirror",
                                "synced_at": STAMP, "generated_at": STAMP}}


def test_write_source_manifest_content_has_no_signed_url_or_absolute_path(tmp_path):
    dest = tmp_path / "student_folder"
    dest.mkdir()
    report_local_reads.write_source_manifest(str(dest), {
        "111": {"course_name": "Course One", "source": "mirror",
                "synced_at": STAMP, "generated_at": STAMP},
    })

    raw_text = (dest / "_source_manifest.json").read_text(encoding="utf-8")
    assert "http://" not in raw_text and "https://" not in raw_text
    assert str(dest) not in raw_text  # no absolute filesystem path in content
    assert str(tmp_path) not in raw_text
