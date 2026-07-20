"""First fetch-level test coverage for
`api/portfolio_service.py::build_merged_portfolios`.

`api/tests/test_portfolio_merged.py` only covers the pure rendering/parsing
layer (entry building, chronological sort, attachment embedding) and
explicitly does not exercise the live-fetch path — this file establishes that
coverage from scratch, proving the 1.0beta-06b migration: one whole-course
local read per run (not one per student), the lazy-session pattern, and the
focused per-submission attachment fetch for ``online_upload`` records.

Every test drives the *real* private mirror through `api/mirror/store.py` (no
store-level monkeypatching) and only fakes the Canvas-reaching transport
functions (`_get_all_pages`, `_fetch_submission`, `_download_binary`) so a
stray live call fails loudly instead of silently degrading into a "skipped"
line.
"""
from __future__ import annotations

import json
import os

import pytest

from api import portfolio_service, report_local_reads
from api.mirror import store
from api.webui import workspace

COURSE_ID = "333"
ASSIGNMENT_TEXT = "800010"
ASSIGNMENT_UPLOAD = "800020"
STAMP = "2026-07-18T12:00:00Z"


@pytest.fixture(autouse=True)
def _workspace(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    # STAMP below is a fixed historical timestamp, older than the real
    # serve-age bound (default 6h) by the time this suite actually runs.
    # Neutralize that bound so existing "local current" fixtures keep
    # resolving to the mirror path regardless of wall-clock time.
    monkeypatch.setattr(report_local_reads.mirror_queries, "_serve_max_age_hours", lambda: 1e9)
    return tmp_path


def _course_dict():
    return {"id": COURSE_ID, "name": "Sample Course"}


def _students(*ids_names):
    return [{"id": uid, "name": name} for uid, name in ids_names]


def _seed_local_current_course(rows):
    store.write_assignments(COURSE_ID, [
        {"id": ASSIGNMENT_TEXT, "name": "Essay 1", "due_at": "2026-07-01T23:59:00Z",
         "points_possible": 10, "published": True, "submission_types": ["online_text_entry"]},
        {"id": ASSIGNMENT_UPLOAD, "name": "Scan 1", "due_at": "2026-07-05T23:59:00Z",
         "points_possible": 10, "published": True, "submission_types": ["online_upload"]},
    ], attempted_at=STAMP)
    by_assignment: dict = {}
    for row in rows:
        by_assignment.setdefault(row["assignment_id"], []).append(row)
    for assignment_id, assignment_rows in by_assignment.items():
        store.merge_submissions(COURSE_ID, assignment_id, assignment_rows,
                                attempted_at=STAMP, replace=True)
    store.record_pass(COURSE_ID, "full", ok=True, attempted_at=STAMP)
    # The comment scope's own sidecar must also be current -- 1.0beta-06e
    # requires it alongside assignments for the mirror path to be used.
    store.record_submission_comments_state(COURSE_ID, ok=True, attempted_at=STAMP)


def _forbid_canvas_calls(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("a Canvas-reaching function was invoked in a fully-local run")
    monkeypatch.setattr(portfolio_service, "_get_all_pages", _boom)
    monkeypatch.setattr(portfolio_service, "_fetch_submission", _boom)
    monkeypatch.setattr(portfolio_service, "_download_binary", _boom)


# --- (b) not-current course: live fallback, one _get_all_pages call per student ----

def test_not_current_course_falls_back_to_one_live_call_per_student(tmp_path, monkeypatch):
    # Assignments exist, but no "full"/"delta" pass was ever recorded for
    # submissions -> private_submissions reports state other than "current".
    store.write_assignments(COURSE_ID, [{
        "id": ASSIGNMENT_TEXT, "name": "Essay 1", "due_at": "", "points_possible": 10,
        "published": True, "submission_types": ["online_text_entry"],
    }], attempted_at=STAMP)
    assert report_local_reads.local_course_submissions_by_user(COURSE_ID) is None

    calls = []

    def fake_get_all_pages(session, url, params):
        calls.append((url, dict(params)))
        return [{
            "assignment_id": ASSIGNMENT_TEXT, "user_id": params["student_ids[]"],
            "workflow_state": "submitted", "submitted_at": STAMP, "score": 9,
            "submission_type": "online_text_entry", "body": "Essay text",
            "assignment": {"id": ASSIGNMENT_TEXT, "name": "Essay 1", "points_possible": 10},
        }]

    monkeypatch.setattr(portfolio_service, "_get_all_pages", fake_get_all_pages)

    students = _students(("900001", "Learner One"), ("900002", "Learner Two"))
    lines = list(portfolio_service.build_merged_portfolios(
        _course_dict(), students, None, None,
        "https://canvas.test", "tok", str(tmp_path / "reports")))

    assert len(calls) == 2  # one live call per student — unchanged from today
    for url, params in calls:
        assert url == f"https://canvas.test/api/v1/courses/{COURSE_ID}/students/submissions"
        assert params["include[]"] == ["assignment"]
        assert params["per_page"] == 100
    assert any(line.startswith("FOLDER:") for line in lines)


# --- (c) mixed cohort: fetch_submission only for online_upload, once per submission ---

def test_mixed_cohort_triggers_fetch_submission_only_for_online_upload_submissions(tmp_path, monkeypatch):
    rows = [
        {"assignment_id": ASSIGNMENT_TEXT, "user_id": "900001", "workflow_state": "submitted",
         "submitted_at": STAMP, "score": 9, "submission_type": "online_text_entry", "body": "Essay text"},
        {"assignment_id": ASSIGNMENT_UPLOAD, "user_id": "900002", "workflow_state": "submitted",
         "submitted_at": STAMP, "score": 8, "submission_type": "online_upload", "body": ""},
        {"assignment_id": ASSIGNMENT_UPLOAD, "user_id": "900003", "workflow_state": "submitted",
         "submitted_at": STAMP, "score": 7, "submission_type": "online_upload", "body": ""},
    ]
    _seed_local_current_course(rows)

    fetch_calls = []

    def fake_fetch_submission(session, base, course_id, assignment_id, user_id):
        fetch_calls.append((course_id, assignment_id, user_id))
        return {"attachments": [{"filename": "scan.png", "url": "https://signed.example/scan.png"}]}

    monkeypatch.setattr(portfolio_service, "_fetch_submission", fake_fetch_submission)
    monkeypatch.setattr(portfolio_service, "_download_binary", lambda session, url, dest: None)
    monkeypatch.setattr(portfolio_service, "_get_all_pages", lambda *a, **k: (_ for _ in ())
                        .throw(AssertionError("whole-course fetch must not be called")))

    students = _students(("900001", "Learner One"), ("900002", "Learner Two"), ("900003", "Learner Three"))
    list(portfolio_service.build_merged_portfolios(
        _course_dict(), students, None, None,
        "https://canvas.test", "tok", str(tmp_path / "reports")))

    assert sorted(fetch_calls) == sorted([
        (COURSE_ID, ASSIGNMENT_UPLOAD, "900002"),
        (COURSE_ID, ASSIGNMENT_UPLOAD, "900003"),
    ])
    assert len(fetch_calls) == 2  # exactly once per online_upload submission, not per student


def test_online_upload_never_triggers_fetch_for_a_student_with_no_local_records(tmp_path, monkeypatch):
    rows = [
        {"assignment_id": ASSIGNMENT_UPLOAD, "user_id": "900002", "workflow_state": "submitted",
         "submitted_at": STAMP, "score": 8, "submission_type": "online_upload", "body": ""},
    ]
    _seed_local_current_course(rows)

    fetch_calls = []
    monkeypatch.setattr(portfolio_service, "_fetch_submission",
                        lambda *a, **k: fetch_calls.append(a) or None)
    monkeypatch.setattr(portfolio_service, "_get_all_pages", lambda *a, **k: (_ for _ in ())
                        .throw(AssertionError("whole-course fetch must not be called")))

    # "900099" has no submissions in this course at all (empty local record set).
    students = _students(("900099", "Learner Absent"))
    lines = list(portfolio_service.build_merged_portfolios(
        _course_dict(), students, None, None,
        "https://canvas.test", "tok", str(tmp_path / "reports")))

    assert fetch_calls == []
    assert any("no writing found" in line for line in lines)


# --- (d) local-current, no upload anywhere -> zero Canvas calls total for the run ---

def test_local_current_no_upload_cohort_makes_zero_canvas_calls(tmp_path, monkeypatch):
    rows = [
        {"assignment_id": ASSIGNMENT_TEXT, "user_id": "900001", "workflow_state": "submitted",
         "submitted_at": STAMP, "score": 9, "submission_type": "online_text_entry", "body": "Essay one"},
        {"assignment_id": ASSIGNMENT_TEXT, "user_id": "900002", "workflow_state": "submitted",
         "submitted_at": STAMP, "score": 8, "submission_type": "online_text_entry", "body": "Essay two"},
    ]
    _seed_local_current_course(rows)
    _forbid_canvas_calls(monkeypatch)

    students = _students(("900001", "Learner One"), ("900002", "Learner Two"))
    lines = list(portfolio_service.build_merged_portfolios(
        _course_dict(), students, None, None,
        "https://canvas.test", "tok", str(tmp_path / "reports")))

    assert not any("skipped" in line for line in lines)
    assert any(line.startswith("✓ Learner One") for line in lines)
    assert any(line.startswith("✓ Learner Two") for line in lines)
    assert any(line.startswith("FOLDER:") for line in lines)


# --- the whole point of the brief: one local read per run, not one per student ------

def test_local_course_submissions_by_user_called_exactly_once_per_run(tmp_path, monkeypatch):
    rows = [
        {"assignment_id": ASSIGNMENT_TEXT, "user_id": "900001", "workflow_state": "submitted",
         "submitted_at": STAMP, "score": 9, "submission_type": "online_text_entry", "body": "Essay one"},
        {"assignment_id": ASSIGNMENT_TEXT, "user_id": "900002", "workflow_state": "submitted",
         "submitted_at": STAMP, "score": 8, "submission_type": "online_text_entry", "body": "Essay two"},
        {"assignment_id": ASSIGNMENT_TEXT, "user_id": "900003", "workflow_state": "submitted",
         "submitted_at": STAMP, "score": 7, "submission_type": "online_text_entry", "body": "Essay three"},
    ]
    _seed_local_current_course(rows)

    calls = []
    original = report_local_reads.local_course_submissions_by_user

    def _spy(course_id, **kwargs):
        calls.append(course_id)
        return original(course_id, **kwargs)

    monkeypatch.setattr(portfolio_service.report_local_reads,
                        "local_course_submissions_by_user", _spy)

    students = _students(("900001", "Learner One"), ("900002", "Learner Two"),
                         ("900003", "Learner Three"))
    list(portfolio_service.build_merged_portfolios(
        _course_dict(), students, None, None,
        "https://canvas.test", "tok", str(tmp_path / "reports")))

    assert calls == [COURSE_ID]  # exactly once for the whole cohort, not once per student


# --- (a) grouped result matches per-student local_course_submissions for this cohort ---

def test_local_course_submissions_by_user_matches_per_student_reads(tmp_path):
    rows = [
        {"assignment_id": ASSIGNMENT_TEXT, "user_id": "900001", "workflow_state": "submitted",
         "submitted_at": STAMP, "score": 9, "submission_type": "online_text_entry", "body": "Essay one"},
        {"assignment_id": ASSIGNMENT_UPLOAD, "user_id": "900002", "workflow_state": "submitted",
         "submitted_at": STAMP, "score": 8, "submission_type": "online_upload", "body": ""},
    ]
    _seed_local_current_course(rows)

    grouped = report_local_reads.local_course_submissions_by_user(COURSE_ID)
    assert grouped is not None
    for uid in ("900001", "900002"):
        assert grouped.get(uid, []) == report_local_reads.local_course_submissions(COURSE_ID, uid)


# --- 1.0beta-06d: private source/freshness manifest --------------------------------

def test_build_merged_portfolios_writes_source_manifest_for_produced_portfolio(tmp_path):
    rows = [
        {"assignment_id": ASSIGNMENT_TEXT, "user_id": "900001", "workflow_state": "submitted",
         "submitted_at": STAMP, "score": 9, "submission_type": "online_text_entry", "body": "Essay text"},
    ]
    _seed_local_current_course(rows)

    reports_root = str(tmp_path / "reports")
    students = _students(("900001", "Learner One"))
    lines = list(portfolio_service.build_merged_portfolios(
        _course_dict(), students, None, None,
        "https://canvas.test", "tok", reports_root))
    assert any(line.startswith("✓ Learner One") for line in lines)

    stu_dir = os.path.join(reports_root, "Learner One")
    with open(os.path.join(stu_dir, "_source_manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    entry = manifest[COURSE_ID]
    assert entry["course_name"] == "Sample Course"
    assert entry["source"] == "mirror"
    assert entry["synced_at"] == STAMP
    assert entry["generated_at"]


def test_build_merged_portfolios_skips_source_manifest_for_no_writing_found(tmp_path, monkeypatch):
    # "Learner Absent" has no local records in this course at all -> the
    # per-student loop produces zero entries and takes the "no writing
    # found" branch, writing no DOCX. Per this brief's default assumption
    # (no manifest for a course that produced no output), the sidecar must
    # not be written for this student either.
    rows = [
        {"assignment_id": ASSIGNMENT_UPLOAD, "user_id": "900002", "workflow_state": "submitted",
         "submitted_at": STAMP, "score": 8, "submission_type": "online_upload", "body": ""},
    ]
    _seed_local_current_course(rows)
    _forbid_canvas_calls(monkeypatch)

    reports_root = str(tmp_path / "reports")
    students = _students(("900099", "Learner Absent"))
    lines = list(portfolio_service.build_merged_portfolios(
        _course_dict(), students, None, None,
        "https://canvas.test", "tok", reports_root))
    assert any("no writing found" in line for line in lines)

    stu_dir = os.path.join(reports_root, "Learner Absent")
    assert not os.path.exists(os.path.join(stu_dir, "_source_manifest.json"))


def test_build_merged_portfolios_writes_canvas_source_when_course_not_current(tmp_path, monkeypatch):
    # Assignments exist, but no "full"/"delta" pass was ever recorded for
    # submissions -> the course falls back to the live per-student fetch, and
    # the manifest for a produced portfolio must still record source="canvas".
    store.write_assignments(COURSE_ID, [{
        "id": ASSIGNMENT_TEXT, "name": "Essay 1", "due_at": "", "points_possible": 10,
        "published": True, "submission_types": ["online_text_entry"],
    }], attempted_at=STAMP)
    assert report_local_reads.local_course_submissions_by_user(COURSE_ID) is None

    def fake_get_all_pages(session, url, params):
        return [{
            "assignment_id": ASSIGNMENT_TEXT, "user_id": params["student_ids[]"],
            "workflow_state": "submitted", "submitted_at": STAMP, "score": 9,
            "submission_type": "online_text_entry", "body": "Essay text",
            "assignment": {"id": ASSIGNMENT_TEXT, "name": "Essay 1", "points_possible": 10},
        }]
    monkeypatch.setattr(portfolio_service, "_get_all_pages", fake_get_all_pages)

    reports_root = str(tmp_path / "reports")
    students = _students(("900001", "Learner One"))
    lines = list(portfolio_service.build_merged_portfolios(
        _course_dict(), students, None, None,
        "https://canvas.test", "tok", reports_root))
    assert any(line.startswith("✓ Learner One") for line in lines)

    stu_dir = os.path.join(reports_root, "Learner One")
    with open(os.path.join(stu_dir, "_source_manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    entry = manifest[COURSE_ID]
    assert entry["source"] == "canvas"
    assert entry["synced_at"] == ""
