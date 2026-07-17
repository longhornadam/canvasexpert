"""Offline tests for the CanvasMirror sync passes.

Canvas is a fake ``canvas_get_all`` closure dispatching on path + params —
the sync module never touches the real client (it is injected, catalog
pattern). Clock is injected via ``now=``.
"""
from __future__ import annotations

import json

from api.mirror import store, sync

COURSE = "111"
NOW = "2026-07-16T12:00:00Z"
NOW_MINUS_OVERLAP = "2026-07-16T11:50:00Z"

USERS = [
    {"id": 900001, "name": "Learner One", "sortable_name": "One, Learner",
     "short_name": "Lee", "sis_user_id": "SIS-900001",
     "enrollments": [{"course_section_id": 800001}]},
]
SECTIONS = [{"id": 800001, "name": "Period 1"}]
ASSIGNMENTS = [
    {"id": 700010, "name": "Essay 1", "due_at": "2026-07-01T23:59:00Z",
     "points_possible": 10, "published": True, "html_url": "u1",
     "submission_types": ["online_text_entry"], "updated_at": ""},
    {"id": 700020, "name": "Essay 2", "due_at": "2026-07-08T23:59:00Z",
     "points_possible": 10, "published": True, "html_url": "u2",
     "submission_types": ["online_text_entry"], "updated_at": ""},
]


def _sub(assignment_id, attempt=1, body="Draft.", **overrides):
    row = {
        "assignment_id": assignment_id, "user_id": 900001,
        "workflow_state": "submitted",
        "submitted_at": f"2026-07-0{attempt}T10:00:00Z", "graded_at": None,
        "score": None, "grade": None, "late": False, "missing": False,
        "excused": False, "attempt": attempt,
        "grade_matches_current_submission": True,
        "submission_type": "online_text_entry", "body": body,
    }
    row.update(overrides)
    return row


class FakeCanvas:
    """Dispatches on URL suffix; records every call for param assertions."""

    def __init__(self, *, assignments=None, users=None, sections=None,
                 submissions=None, delta_submitted=None, delta_graded=None,
                 errors=None):
        self.assignments = assignments if assignments is not None else list(ASSIGNMENTS)
        self.users = users if users is not None else list(USERS)
        self.sections = sections if sections is not None else list(SECTIONS)
        self.submissions = submissions or []
        self.delta_submitted = delta_submitted or []
        self.delta_graded = delta_graded or []
        self.errors = errors or {}
        self.calls = []

    def __call__(self, path, params=None, timeout=30):
        self.calls.append((path, dict(params or {})))
        if path.endswith("/assignments"):
            return (None, self.errors["assignments"]) if "assignments" in self.errors \
                else (self.assignments, None)
        if path.endswith("/users"):
            return (None, self.errors["users"]) if "users" in self.errors \
                else (self.users, None)
        if path.endswith("/sections"):
            return self.sections, None
        if path.endswith("/students/submissions"):
            if "submissions" in self.errors:
                return None, self.errors["submissions"]
            if "submitted_since" in (params or {}):
                return self.delta_submitted, None
            if "graded_since" in (params or {}):
                return self.delta_graded, None
            return self.submissions, None
        raise AssertionError(f"unexpected path {path}")


# --- full pass ---------------------------------------------------------------

def test_full_pass_writes_everything_and_sets_watermarks(tmp_path):
    canvas = FakeCanvas(submissions=[_sub(700010), _sub(700020)])
    result = sync.full_pass(COURSE, canvas_get_all=canvas, root=str(tmp_path), now=NOW)
    assert result["ok"] is True
    assert result["assignments"] == 2
    assert store.read_roster(COURSE, root=str(tmp_path))["students"]["900001"]["name"] == "Learner One"
    assert set(store.read_assignments(COURSE, root=str(tmp_path))["assignments"]) == {"700010", "700020"}
    assert store.read_submissions(COURSE, "700010", root=str(tmp_path))["submissions"]["900001"]
    state = store.read_sync(COURSE, root=str(tmp_path))
    assert state["passes"]["full"]["state"] == "current"
    assert state["passes"]["roster"]["state"] == "current"
    assert state["watermarks"] == {"submitted_since": NOW_MINUS_OVERLAP,
                                   "graded_since": NOW_MINUS_OVERLAP}


def test_full_pass_requests_submission_comments_delta_does_not(tmp_path):
    canvas = FakeCanvas(submissions=[_sub(700010)])
    sync.full_pass(COURSE, canvas_get_all=canvas, root=str(tmp_path), now=NOW)
    full_submissions_call = next(
        params for path, params in canvas.calls
        if path.endswith("/students/submissions") and "submitted_since" not in params
        and "graded_since" not in params)
    assert full_submissions_call["include[]"] == ["submission_history", "submission_comments"]

    delta_canvas = FakeCanvas(delta_submitted=[_sub(700010, attempt=2)])
    sync.delta_pass(COURSE, canvas_get_all=delta_canvas, root=str(tmp_path),
                    now="2026-07-16T13:00:00Z")
    submitted_call = next(p for path, p in delta_canvas.calls if "submitted_since" in p)
    graded_call = next(p for path, p in delta_canvas.calls if "graded_since" in p)
    assert "submission_comments" not in submitted_call.get("include[]", [])
    assert "include[]" not in graded_call


def test_full_pass_captures_submission_comments(tmp_path):
    canvas = FakeCanvas(submissions=[
        _sub(700010, submission_comments=[
            {"author_id": 900099, "comment": "Nice work.",
             "created_at": "2026-07-01T11:00:00Z", "author_name": "Teacher T"},
        ]),
    ])
    result = sync.full_pass(COURSE, canvas_get_all=canvas, root=str(tmp_path), now=NOW)
    assert result["ok"] is True
    entry = store.read_submissions(COURSE, "700010", root=str(tmp_path))["submissions"]["900001"]
    assert entry["current"]["submission_comments"] == [
        {"author_id": "900099", "comment": "Nice work.",
         "created_at": "2026-07-01T11:00:00Z"},
    ]
    assert "author_name" not in entry["current"]["submission_comments"][0]


def test_delta_after_full_does_not_erase_stored_comments(tmp_path):
    canvas = FakeCanvas(submissions=[
        _sub(700010, submission_comments=[
            {"author_id": 900099, "comment": "Nice work.",
             "created_at": "2026-07-01T11:00:00Z"},
        ]),
    ])
    sync.full_pass(COURSE, canvas_get_all=canvas, root=str(tmp_path), now=NOW)
    # Delta fetches (lean, no submission_comments include) never carry comments.
    delta_canvas = FakeCanvas(delta_submitted=[_sub(700010, attempt=2, body="Second draft.")])
    result = sync.delta_pass(COURSE, canvas_get_all=delta_canvas, root=str(tmp_path),
                             now="2026-07-16T13:00:00Z")
    assert result["ok"] is True
    entry = store.read_submissions(COURSE, "700010", root=str(tmp_path))["submissions"]["900001"]
    assert entry["current"]["submission_comments"] == [
        {"author_id": "900099", "comment": "Nice work.",
         "created_at": "2026-07-01T11:00:00Z"},
    ]
    assert entry["current"]["attempt"] == 2


def test_mcp_get_submissions_never_leaks_comment_text(monkeypatch, tmp_path):
    from api.feedback_vault import Vault
    from api.mcp_server import tools
    from api.webui import workspace

    canvas = FakeCanvas(submissions=[
        _sub(700010, submission_comments=[
            {"author_id": 900099, "comment": "SECRET-FEEDBACK-TEXT",
             "created_at": "2026-07-01T11:00:00Z"},
        ]),
    ])
    # Real now_iso() (not the fixed NOW fixture) so the mirror-serve
    # freshness gate — which compares against wall-clock time — passes.
    sync.full_pass(COURSE, canvas_get_all=canvas, root=str(tmp_path), now=store.now_iso())

    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    monkeypatch.setattr(tools.config, "active_courses", lambda: [{"id": COURSE}])
    monkeypatch.setattr(tools, "_vault_factory",
                        lambda: Vault(str(tmp_path / "vault.json")))
    result = tools.get_submissions(COURSE, "700010")
    assert result["ok"] is True
    dumped = json.dumps(result)
    assert "SECRET-FEEDBACK-TEXT" not in dumped
    assert "submission_comments" not in dumped


def test_full_pass_prunes_deleted_assignments_and_dropped_students(tmp_path):
    canvas = FakeCanvas(submissions=[_sub(700010), _sub(700020)])
    sync.full_pass(COURSE, canvas_get_all=canvas, root=str(tmp_path), now=NOW)
    # Canvas now says: assignment 700020 gone; 900001 no longer has a row on 700010.
    later = FakeCanvas(assignments=[ASSIGNMENTS[0]], submissions=[
        _sub(700010, user_id=900002),
    ])
    result = sync.full_pass(COURSE, canvas_get_all=later, root=str(tmp_path),
                            now="2026-07-17T03:00:00Z")
    assert result["pruned_assignments"] == ["700020"]
    assert store.read_submissions(COURSE, "700020", root=str(tmp_path)) is None
    document = store.read_submissions(COURSE, "700010", root=str(tmp_path))
    assert set(document["submissions"]) == {"900002"}


def test_full_pass_fetch_error_records_failure_and_writes_nothing(tmp_path):
    canvas = FakeCanvas(errors={"submissions": "HTTP 503: upstream"})
    result = sync.full_pass(COURSE, canvas_get_all=canvas, root=str(tmp_path), now=NOW)
    assert result["ok"] is False
    state = store.read_sync(COURSE, root=str(tmp_path))
    assert state["passes"]["full"]["state"] == "unavailable"
    assert state["watermarks"]["submitted_since"] == ""
    assert store.read_assignments(COURSE, root=str(tmp_path)) is None


# --- delta pass ----------------------------------------------------------------

def _backfilled(tmp_path, submissions=None):
    canvas = FakeCanvas(submissions=submissions if submissions is not None
                        else [_sub(700010)])
    assert sync.full_pass(COURSE, canvas_get_all=canvas, root=str(tmp_path),
                          now=NOW)["ok"] is True


def test_delta_pass_without_watermarks_falls_back_to_full(tmp_path):
    canvas = FakeCanvas(submissions=[_sub(700010)])
    result = sync.delta_pass(COURSE, canvas_get_all=canvas, root=str(tmp_path), now=NOW)
    assert result["ok"] is True
    assert "submission_rows" in result  # full-pass result shape
    assert store.read_sync(COURSE, root=str(tmp_path))["passes"]["full"]["state"] == "current"


def test_delta_pass_sends_watermarks_and_merges_new_attempt(tmp_path):
    _backfilled(tmp_path)
    canvas = FakeCanvas(delta_submitted=[
        _sub(700010, attempt=2, body="Second draft.", submission_history=[
            {"attempt": 2, "submitted_at": "2026-07-02T10:00:00Z",
             "submission_type": "online_text_entry", "body": "Second draft."},
        ]),
    ])
    later = "2026-07-16T13:00:00Z"
    result = sync.delta_pass(COURSE, canvas_get_all=canvas, root=str(tmp_path), now=later)
    assert result["ok"] is True
    assert result["touched_assignments"] == ["700010"]

    submitted_call = next(p for path, p in canvas.calls if "submitted_since" in p)
    graded_call = next(p for path, p in canvas.calls if "graded_since" in p)
    assert submitted_call["submitted_since"] == NOW_MINUS_OVERLAP
    assert submitted_call["include[]"] == ["submission_history"]
    assert graded_call["graded_since"] == NOW_MINUS_OVERLAP
    assert "include[]" not in graded_call

    entry = store.read_submissions(COURSE, "700010", root=str(tmp_path))["submissions"]["900001"]
    assert set(entry["attempts"]) == {"1", "2"}  # append-only across the delta
    assert entry["current"]["attempt"] == 2
    state = store.read_sync(COURSE, root=str(tmp_path))
    assert state["watermarks"]["submitted_since"] == "2026-07-16T12:50:00Z"


def test_delta_pass_is_idempotent_on_replay(tmp_path):
    _backfilled(tmp_path)
    delta = [_sub(700010, attempt=2, body="Second draft.")]
    for stamp in ("2026-07-16T13:00:00Z", "2026-07-16T13:00:00Z"):
        canvas = FakeCanvas(delta_submitted=list(delta))
        sync.delta_pass(COURSE, canvas_get_all=canvas, root=str(tmp_path), now=stamp)
    entry = store.read_submissions(COURSE, "700010", root=str(tmp_path))["submissions"]["900001"]
    assert set(entry["attempts"]) == {"1", "2"}
    assert entry["current"]["attempt"] == 2


def test_delta_pass_graded_only_change_updates_current(tmp_path):
    _backfilled(tmp_path)
    canvas = FakeCanvas(delta_graded=[
        _sub(700010, workflow_state="graded", score=9, grade="9",
             graded_at="2026-07-16T12:30:00Z"),
    ])
    result = sync.delta_pass(COURSE, canvas_get_all=canvas, root=str(tmp_path),
                             now="2026-07-16T13:00:00Z")
    assert result["ok"] is True
    current = store.read_submissions(COURSE, "700010", root=str(tmp_path))["submissions"]["900001"]["current"]
    assert current["score"] == 9
    assert current["workflow_state"] == "graded"


def test_delta_pass_error_keeps_watermarks(tmp_path):
    _backfilled(tmp_path)
    canvas = FakeCanvas(errors={"submissions": "HTTP 503: upstream"})
    result = sync.delta_pass(COURSE, canvas_get_all=canvas, root=str(tmp_path),
                             now="2026-07-16T13:00:00Z")
    assert result["ok"] is False
    state = store.read_sync(COURSE, root=str(tmp_path))
    assert state["passes"]["delta"]["state"] == "unavailable"  # never succeeded
    assert state["watermarks"]["submitted_since"] == NOW_MINUS_OVERLAP  # unchanged


# --- roster pass ------------------------------------------------------------------

def test_roster_pass_updates_roster_only(tmp_path):
    canvas = FakeCanvas()
    result = sync.roster_pass(COURSE, canvas_get_all=canvas, root=str(tmp_path), now=NOW)
    assert result == {"ok": True, "students": 1}
    assert store.read_roster(COURSE, root=str(tmp_path)) is not None
    assert store.read_assignments(COURSE, root=str(tmp_path)) is None
    assert store.read_sync(COURSE, root=str(tmp_path))["passes"]["roster"]["state"] == "current"


def test_roster_pass_failure_degrades(tmp_path):
    canvas = FakeCanvas()
    sync.roster_pass(COURSE, canvas_get_all=canvas, root=str(tmp_path), now=NOW)
    failing = FakeCanvas(errors={"users": "HTTP 401: token"})
    result = sync.roster_pass(COURSE, canvas_get_all=failing, root=str(tmp_path),
                              now="2026-07-16T13:00:00Z")
    assert result["ok"] is False
    entry = store.read_sync(COURSE, root=str(tmp_path))["passes"]["roster"]
    assert entry["state"] == "stale"
    assert entry["last_success_at"] == NOW


# --- workspace guard -----------------------------------------------------------------

def test_passes_report_unconfigured_workspace(monkeypatch):
    from api.webui import workspace
    monkeypatch.setattr(workspace, "workspace_root", lambda: None)
    result = sync.full_pass(COURSE, canvas_get_all=FakeCanvas())
    assert result == {"ok": False, "error": "workspace not configured"}
