"""PowerGrader session creation: focused assignment refresh then disk.

Synthetic data only. Text-entry sessions refresh exactly one assignment and
serve disk only when roster identities can rebuild Canvas's nested user shape.
Every unsafe lane keeps its existing live fetch.
"""
from __future__ import annotations

from api.mirror import store
from api.powergrader import canvas_fetch
from api.platform_services import workspace


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

ROSTER = [{
    "id": 800101, "name": "Learner Fictional", "sortable_name": "Fictional, Learner",
    "short_name": "Learner F", "sis_user_id": "SIS-800101", "enrollments": [],
}]


def _submission(*, user_id=STUDENT, attempt=1, body="Draft."):
    return {
        "assignment_id": ASSIGNMENT, "user_id": user_id,
        "workflow_state": "submitted", "submitted_at": "2026-07-15T10:00:00Z",
        "graded_at": None, "score": None, "grade": None, "late": False,
        "missing": False, "excused": False, "attempt": attempt,
        "grade_matches_current_submission": None,
        "submission_type": "online_text_entry", "body": body,
    }


def _raise_if_called(label):
    def _explode(*_args, **_kwargs):
        raise AssertionError(label)
    return _explode


def _populate_mirror(root, *, rows, roster=ROSTER):
    if roster is not None:
        store.write_roster(COURSE, roster, {}, root=root)
    store.merge_submissions(COURSE, ASSIGNMENT, rows, root=root, replace=True)


def _mock_assignment_get(monkeypatch, adata):
    monkeypatch.setattr(canvas_fetch, "canvas_get", lambda *_a, **_k: (dict(adata), None))


def test_successful_focused_refresh_serves_complete_roster_rows_without_live_fetch(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    _mock_assignment_get(monkeypatch, ADATA_TEXT_ONLY)
    _populate_mirror(str(tmp_path), rows=[_submission(body="Old disk body.")])
    calls = []

    def focused_canvas(path, params=None, timeout=30):
        calls.append((path, dict(params or {})))
        if path.endswith(f"/assignments/{ASSIGNMENT}/submissions"):
            return [_submission(attempt=2, body="Focused current reflection.")], None
        raise AssertionError("live submission fetch must not run")

    monkeypatch.setattr(canvas_fetch, "canvas_get_all", focused_canvas)
    subs, adata, error = canvas_fetch.fetch_submissions(COURSE, ASSIGNMENT)

    assert error is None
    assert calls == [(
        f"/api/v1/courses/{COURSE}/assignments/{ASSIGNMENT}/submissions",
        {"per_page": 100, "include[]": ["submission_history"]},
    )]
    assert subs[0]["body"] == "Focused current reflection."
    assert subs[0]["user"]["name"] == "Learner Fictional"
    assert subs[0]["assignment"]["description"] == "Write a short reflection."
    assert adata["id"] == ASSIGNMENT


def test_failed_focused_refresh_keeps_last_good_and_falls_back_to_live(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    _mock_assignment_get(monkeypatch, ADATA_TEXT_ONLY)
    _populate_mirror(str(tmp_path), rows=[_submission(body="STALE - must not be returned.")])
    live_rows = [{"user_id": STUDENT, "body": "Live fallback body.",
                  "submission_type": "online_text_entry", "workflow_state": "submitted"}]

    def failing_focused_canvas(path, params=None, timeout=30):
        if path.endswith(f"/assignments/{ASSIGNMENT}/submissions"):
            return None, "HTTP 503: upstream"
        if path.endswith("/students/submissions"):
            return live_rows, None
        raise AssertionError(f"unexpected path {path}")

    monkeypatch.setattr(canvas_fetch, "canvas_get_all", failing_focused_canvas)
    subs, _adata, error = canvas_fetch.fetch_submissions(COURSE, ASSIGNMENT)

    assert error is None
    assert subs == live_rows
    document = store.read_submissions(COURSE, ASSIGNMENT, root=str(tmp_path))
    assert document["submissions"][STUDENT]["current"]["body"] == "STALE - must not be returned."


def test_incomplete_roster_falls_back_to_live_canvas_users(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    _mock_assignment_get(monkeypatch, ADATA_TEXT_ONLY)
    _populate_mirror(str(tmp_path), rows=[], roster=ROSTER)
    live_rows = [{"user_id": "800102", "body": "Live named row.",
                  "submission_type": "online_text_entry", "workflow_state": "submitted",
                  "user": {"id": "800102", "name": "Live Learner"}}]

    def incomplete_roster_canvas(path, params=None, timeout=30):
        if path.endswith(f"/assignments/{ASSIGNMENT}/submissions"):
            return [_submission(user_id="800102", body="Do not serve this disk row.")], None
        if path.endswith("/students/submissions"):
            return live_rows, None
        raise AssertionError(f"unexpected path {path}")

    monkeypatch.setattr(canvas_fetch, "canvas_get_all", incomplete_roster_canvas)
    subs, _adata, error = canvas_fetch.fetch_submissions(COURSE, ASSIGNMENT)

    assert error is None
    assert subs == live_rows


def test_empty_focused_result_is_servable_without_a_roster(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    _mock_assignment_get(monkeypatch, ADATA_TEXT_ONLY)

    def focused_empty_canvas(path, params=None, timeout=30):
        if path.endswith(f"/assignments/{ASSIGNMENT}/submissions"):
            return [], None
        raise AssertionError("live submission fetch must not run")

    monkeypatch.setattr(canvas_fetch, "canvas_get_all", focused_empty_canvas)
    subs, _adata, error = canvas_fetch.fetch_submissions(COURSE, ASSIGNMENT)

    assert error is None
    assert subs == []


def test_upload_capable_assignment_never_attempts_the_focused_path(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    _mock_assignment_get(monkeypatch, ADATA_UPLOAD_CAPABLE)
    monkeypatch.setattr(canvas_fetch.mirror_sync, "sync_assignment_submissions",
                        _raise_if_called("focused refresh must not run for upload-capable work"))
    live_rows = [{"user_id": STUDENT, "submission_type": "online_upload",
                  "workflow_state": "submitted", "attachments": [
                      {"filename": "essay.pdf", "url": "https://canvas.test/files/1", "size": 10},
                  ]}]
    monkeypatch.setattr(canvas_fetch, "canvas_get_all", lambda *_a, **_k: (live_rows, None))

    subs, _adata, error = canvas_fetch.fetch_submissions(COURSE, ASSIGNMENT)

    assert error is None
    assert subs == live_rows


def test_explicit_materialization_keeps_text_entry_on_live_path(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    _mock_assignment_get(monkeypatch, ADATA_TEXT_ONLY)
    monkeypatch.setattr(canvas_fetch.mirror_sync, "sync_assignment_submissions",
                        _raise_if_called("focused refresh must not run when materializing files"))
    live_rows = [{"user_id": STUDENT, "submission_type": "online_text_entry",
                  "workflow_state": "submitted", "body": "Live materialized body."}]
    monkeypatch.setattr(canvas_fetch, "canvas_get_all", lambda *_a, **_k: (live_rows, None))

    subs, _adata, error = canvas_fetch.fetch_submissions(
        COURSE, ASSIGNMENT, materialize_ordinary_files=True,
    )

    assert error is None
    assert subs == live_rows


def test_new_quiz_lti_assignment_never_attempts_the_focused_path(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    _mock_assignment_get(monkeypatch, {**ADATA_TEXT_ONLY, "is_quiz_lti_assignment": True})
    monkeypatch.setattr(canvas_fetch.mirror_sync, "sync_assignment_submissions",
                        _raise_if_called("focused refresh must not run for the New Quiz flow"))
    live_rows = [{"user_id": STUDENT, "submission_type": "external_tool", "workflow_state": "submitted"}]
    monkeypatch.setattr(canvas_fetch, "canvas_get_all", lambda *_a, **_k: (live_rows, None))

    from api.powergrader import new_quiz_fetch
    monkeypatch.setattr(new_quiz_fetch, "fetch", lambda *args, **kwargs: ([], None))
    _subs, adata, error = canvas_fetch.fetch_submissions(COURSE, ASSIGNMENT)

    assert error is None
    assert adata["is_quiz_lti_assignment"] is True
