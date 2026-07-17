"""Slice 4 — PowerGrader session creation: delta-then-disk.

``canvas_fetch.fetch_submissions`` may read ordinary submission bodies from
the CanvasMirror only immediately after a synchronous delta for that course
succeeds (locked decision 5). Any failure — a failed delta, a mirror read
error, an assignment whose submission types could carry a real Canvas
attachment, or an explicit request for attachment materialization — must
fall back to the existing live paginated fetch, unchanged.

Synthetic data only: fake names, ids in the 900000s/700000s/800000s range.
"""
from __future__ import annotations

import pytest

from api.mirror import store
from api.powergrader import canvas_fetch
from api.webui import mirror_service, workspace


COURSE = "900101"
ASSIGNMENT = "700101"
STUDENT = "800101"

ADATA_TEXT_ONLY = {
    "id": ASSIGNMENT,
    "name": "Reflection Essay",
    "description": "Write a short reflection.",
    "points_possible": 20,
    "submission_types": ["online_text_entry"],
    "is_quiz_lti_assignment": False,
}

ADATA_UPLOAD_CAPABLE = {
    **ADATA_TEXT_ONLY,
    "submission_types": ["online_text_entry", "online_upload"],
}

ROSTER = [
    {"id": 800101, "name": "Learner Fictional", "sortable_name": "Fictional, Learner",
     "short_name": "Learner F", "sis_user_id": "SIS-800101", "enrollments": []},
]


def _raise_if_called(label):
    def _explode(*_args, **_kwargs):
        raise AssertionError(label)
    return _explode


def _populate_mirror(root, *, rows, roster=ROSTER):
    store.write_roster(COURSE, roster, {}, root=root)
    store.merge_submissions(COURSE, ASSIGNMENT, rows, root=root, replace=True)


def _mock_assignment_get(monkeypatch, adata):
    monkeypatch.setattr(canvas_fetch, "_canvas_get", lambda *_a, **_k: (dict(adata), None))


def _ok_sync_now(calls=None):
    def _fake(course_id, **_kwargs):
        if calls is not None:
            calls.append(course_id)
        return [{"course_id": course_id, "pass": "delta", "ok": True, "changed_rows": 0}]
    return _fake


def _failed_sync_now():
    def _fake(course_id, **_kwargs):
        return [{"course_id": course_id, "pass": "delta", "ok": False, "error": "Canvas 503"}]
    return _fake


def test_successful_delta_serves_mirror_rows_without_live_fetch(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    _mock_assignment_get(monkeypatch, ADATA_TEXT_ONLY)
    _populate_mirror(str(tmp_path), rows=[{
        "assignment_id": ASSIGNMENT, "user_id": STUDENT, "workflow_state": "submitted",
        "submitted_at": "2026-07-15T10:00:00Z", "graded_at": None, "score": None,
        "grade": None, "late": False, "missing": False, "excused": False, "attempt": 1,
        "grade_matches_current_submission": None, "submission_type": "online_text_entry",
        "body": "My honest reflection.",
    }])
    sync_calls = []
    monkeypatch.setattr(mirror_service, "sync_now", _ok_sync_now(sync_calls))
    monkeypatch.setattr(canvas_fetch, "_canvas_get_all", _raise_if_called("live submission fetch must not run"))

    subs, adata, error = canvas_fetch.fetch_submissions(COURSE, ASSIGNMENT)

    assert error is None
    assert sync_calls == [COURSE]
    assert len(subs) == 1
    row = subs[0]
    assert row["user_id"] == STUDENT
    assert row["body"] == "My honest reflection."
    # Reconstructed include[]=user,assignment shape (mirror rows store neither).
    assert row["user"]["name"] == "Learner Fictional"
    assert row["assignment"]["description"] == "Write a short reflection."
    assert row["assignment"]["points_possible"] == 20
    assert adata["id"] == ASSIGNMENT


def test_failed_delta_falls_back_to_live_fetch(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    _mock_assignment_get(monkeypatch, ADATA_TEXT_ONLY)
    # Populate the mirror with content that must NOT be served — proves the
    # fallback genuinely re-fetches live rather than reading stale disk.
    _populate_mirror(str(tmp_path), rows=[{
        "assignment_id": ASSIGNMENT, "user_id": STUDENT, "workflow_state": "submitted",
        "submitted_at": "2026-07-01T10:00:00Z", "graded_at": None, "score": None,
        "grade": None, "late": False, "missing": False, "excused": False, "attempt": 1,
        "grade_matches_current_submission": None, "submission_type": "online_text_entry",
        "body": "STALE — must not be returned.",
    }])
    monkeypatch.setattr(mirror_service, "sync_now", _failed_sync_now())
    live_rows = [{"user_id": STUDENT, "body": "Live fallback body.",
                  "submission_type": "online_text_entry", "workflow_state": "submitted"}]
    monkeypatch.setattr(canvas_fetch, "_canvas_get_all", lambda *_a, **_k: (live_rows, None))

    subs, adata, error = canvas_fetch.fetch_submissions(COURSE, ASSIGNMENT)

    assert error is None
    assert subs == live_rows
    assert subs[0]["body"] == "Live fallback body."


def test_mirror_read_error_after_successful_delta_falls_back_to_live(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    _mock_assignment_get(monkeypatch, ADATA_TEXT_ONLY)
    # Delta reports success, but no submissions file was ever written for this
    # assignment (e.g. the course has never had this assignment materialize) —
    # store.read_submissions returns None -> MIRROR_UNAVAILABLE.
    monkeypatch.setattr(mirror_service, "sync_now", _ok_sync_now())
    live_rows = [{"user_id": STUDENT, "body": "Live because mirror read failed.",
                  "submission_type": "online_text_entry", "workflow_state": "submitted"}]
    monkeypatch.setattr(canvas_fetch, "_canvas_get_all", lambda *_a, **_k: (live_rows, None))

    subs, adata, error = canvas_fetch.fetch_submissions(COURSE, ASSIGNMENT)

    assert error is None
    assert subs == live_rows


def test_resubmission_in_mirror_reaches_the_session_as_current(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    _mock_assignment_get(monkeypatch, ADATA_TEXT_ONLY)
    store.write_roster(COURSE, ROSTER, {}, root=str(tmp_path))
    # First pass captures attempt 1; a later delta brings in the resubmission
    # (attempt 2) for the same student — merge_submissions must expose the
    # newest attempt as "current".
    store.merge_submissions(COURSE, ASSIGNMENT, [{
        "assignment_id": ASSIGNMENT, "user_id": STUDENT, "workflow_state": "submitted",
        "submitted_at": "2026-07-14T10:00:00Z", "graded_at": None, "score": None,
        "grade": None, "late": False, "missing": False, "excused": False, "attempt": 1,
        "grade_matches_current_submission": None, "submission_type": "online_text_entry",
        "body": "Draft one.",
    }], root=str(tmp_path), replace=True)
    store.merge_submissions(COURSE, ASSIGNMENT, [{
        "assignment_id": ASSIGNMENT, "user_id": STUDENT, "workflow_state": "submitted",
        "submitted_at": "2026-07-15T09:00:00Z", "graded_at": None, "score": None,
        "grade": None, "late": True, "missing": False, "excused": False, "attempt": 2,
        "grade_matches_current_submission": None, "submission_type": "online_text_entry",
        "body": "Resubmitted final draft.",
    }], root=str(tmp_path), replace=False)
    monkeypatch.setattr(mirror_service, "sync_now", _ok_sync_now())
    monkeypatch.setattr(canvas_fetch, "_canvas_get_all", _raise_if_called("live submission fetch must not run"))

    subs, adata, error = canvas_fetch.fetch_submissions(COURSE, ASSIGNMENT)

    assert error is None
    assert len(subs) == 1
    assert subs[0]["attempt"] == 2
    assert subs[0]["body"] == "Resubmitted final draft."
    assert subs[0]["late"] is True


def test_upload_capable_assignment_never_attempts_the_mirror_path(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    _mock_assignment_get(monkeypatch, ADATA_UPLOAD_CAPABLE)
    _populate_mirror(str(tmp_path), rows=[{
        "assignment_id": ASSIGNMENT, "user_id": STUDENT, "workflow_state": "submitted",
        "submitted_at": "2026-07-15T10:00:00Z", "graded_at": None, "score": None,
        "grade": None, "late": False, "missing": False, "excused": False, "attempt": 1,
        "grade_matches_current_submission": None, "submission_type": "online_upload",
        "body": "",
    }])
    # Even a fresh, servable mirror must not be consulted: mirror rows carry
    # no attachment payload, and this assignment type can carry real files.
    monkeypatch.setattr(mirror_service, "sync_now", _raise_if_called("delta must not run for an upload-capable assignment"))
    live_rows = [{"user_id": STUDENT, "submission_type": "online_upload",
                  "workflow_state": "submitted", "attachments": [
                      {"filename": "essay.pdf", "url": "https://canvas.test/files/1", "size": 10},
                  ]}]
    monkeypatch.setattr(canvas_fetch, "_canvas_get_all", lambda *_a, **_k: (live_rows, None))

    subs, adata, error = canvas_fetch.fetch_submissions(COURSE, ASSIGNMENT)

    assert error is None
    assert subs == live_rows
    assert subs[0]["attachments"][0]["url"] == "https://canvas.test/files/1"


def test_explicit_materialize_flag_forces_live_path_even_for_text_only(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    _mock_assignment_get(monkeypatch, ADATA_TEXT_ONLY)
    _populate_mirror(str(tmp_path), rows=[{
        "assignment_id": ASSIGNMENT, "user_id": STUDENT, "workflow_state": "submitted",
        "submitted_at": "2026-07-15T10:00:00Z", "graded_at": None, "score": None,
        "grade": None, "late": False, "missing": False, "excused": False, "attempt": 1,
        "grade_matches_current_submission": None, "submission_type": "online_text_entry",
        "body": "Would be servable, but the caller asked for materialization.",
    }])
    monkeypatch.setattr(mirror_service, "sync_now", _raise_if_called("delta must not run when materialize_ordinary_files=True"))
    live_rows = [{"user_id": STUDENT, "submission_type": "online_text_entry",
                  "workflow_state": "submitted", "body": "Live because caller opted in to materialization."}]
    monkeypatch.setattr(canvas_fetch, "_canvas_get_all", lambda *_a, **_k: (live_rows, None))

    subs, adata, error = canvas_fetch.fetch_submissions(
        COURSE, ASSIGNMENT, materialize_ordinary_files=True,
    )

    assert error is None
    assert subs == live_rows


def test_new_quiz_lti_assignment_never_attempts_the_mirror_path(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    adata = {**ADATA_TEXT_ONLY, "is_quiz_lti_assignment": True}
    _mock_assignment_get(monkeypatch, adata)
    monkeypatch.setattr(mirror_service, "sync_now", _raise_if_called("delta must not run for the New Quiz flow"))
    live_rows = [{"user_id": STUDENT, "submission_type": "external_tool", "workflow_state": "submitted"}]
    monkeypatch.setattr(canvas_fetch, "_canvas_get_all", lambda *_a, **_k: (live_rows, None))

    from api.powergrader import new_quiz_fetch
    monkeypatch.setattr(new_quiz_fetch, "fetch", lambda *args, **kwargs: ([], None))

    subs, adata_out, error = canvas_fetch.fetch_submissions(COURSE, ASSIGNMENT)

    assert error is None
    assert adata_out["is_quiz_lti_assignment"] is True
