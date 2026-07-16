"""Offline tests for the mirror scheduling service and routes.

The heartbeat thread is never started — tests drive run_heartbeat_pass /
sync_now directly with a fake canvas_get_all and injected now= (house
pattern from test_powergrader_scheduled_autoscore).
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from api.mirror import store
from api.webui import mirror_service, workspace
from api.webui.server import app

NOW = "2026-07-16T12:00:00Z"


class FakeCanvas:
    def __init__(self):
        self.calls = []

    def __call__(self, path, params=None, timeout=30):
        self.calls.append(path)
        if path.endswith("/assignments"):
            return [{"id": 700010, "name": "Essay 1", "published": True}], None
        if path.endswith("/users"):
            return [{"id": 900001, "name": "Learner One"}], None
        if path.endswith("/sections"):
            return [], None
        if path.endswith("/students/submissions"):
            return [], None
        raise AssertionError(f"unexpected path {path}")


def _configure(monkeypatch, tmp_path, courses=({"id": "111", "name": "Course"},)):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    monkeypatch.setattr(mirror_service.config, "token_is_set", lambda: True)
    monkeypatch.setattr(mirror_service.config, "mirror_enabled", lambda: True)
    monkeypatch.setattr(mirror_service.config, "active_courses", lambda: list(courses))


# --- due_passes cadence -----------------------------------------------------

def test_due_passes_full_when_never_synced():
    assert mirror_service.due_passes(store.default_sync("111"), NOW) == ["full"]


def test_due_passes_delta_when_fresh():
    state = store.default_sync("111")
    state["passes"]["full"]["last_success_at"] = "2026-07-16T11:00:00Z"
    state["passes"]["roster"]["last_success_at"] = "2026-07-16T11:00:00Z"
    assert mirror_service.due_passes(state, NOW) == ["delta"]


def test_due_passes_nightly_full_and_daily_roster():
    state = store.default_sync("111")
    state["passes"]["full"]["last_success_at"] = "2026-07-15T11:00:00Z"  # >24h
    assert mirror_service.due_passes(state, NOW) == ["full"]
    state["passes"]["full"]["last_success_at"] = "2026-07-16T11:00:00Z"
    state["passes"]["roster"]["last_success_at"] = "2026-07-15T11:00:00Z"  # >24h
    assert mirror_service.due_passes(state, NOW) == ["delta", "roster"]


# --- heartbeat pass -----------------------------------------------------------

def test_heartbeat_first_tick_backfills_active_courses(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    canvas = FakeCanvas()
    summaries = mirror_service.run_heartbeat_pass(canvas_get_all=canvas, now=NOW)
    assert [(s["course_id"], s["pass"], s["ok"]) for s in summaries] == [("111", "full", True)]
    assert store.read_sync("111")["passes"]["full"]["state"] == "current"


def test_heartbeat_steady_state_runs_delta_only(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    mirror_service.run_heartbeat_pass(canvas_get_all=FakeCanvas(), now=NOW)
    summaries = mirror_service.run_heartbeat_pass(
        canvas_get_all=FakeCanvas(), now="2026-07-16T12:15:00Z")
    assert [s["pass"] for s in summaries] == ["delta"]


def test_heartbeat_gates_on_token_flag_and_workspace(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(mirror_service.config, "token_is_set", lambda: False)
    assert mirror_service.run_heartbeat_pass(canvas_get_all=FakeCanvas(), now=NOW) == []

    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(mirror_service.config, "mirror_enabled", lambda: False)
    assert mirror_service.run_heartbeat_pass(canvas_get_all=FakeCanvas(), now=NOW) == []

    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(workspace, "workspace_root", lambda: None)
    assert mirror_service.run_heartbeat_pass(canvas_get_all=FakeCanvas(), now=NOW) == []


def test_heartbeat_survives_a_course_that_raises(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path,
               courses=({"id": "111"}, {"id": "222"}))

    def exploding(path, params=None, timeout=30):
        if "/222/" in path:
            raise RuntimeError("boom")
        return FakeCanvas()(path, params, timeout)

    summaries = mirror_service.run_heartbeat_pass(canvas_get_all=exploding, now=NOW)
    by_course = {s["course_id"]: s for s in summaries}
    assert by_course["111"]["ok"] is True
    assert by_course["222"]["ok"] is False


# --- sync_now -------------------------------------------------------------------

def test_sync_now_scopes_to_current_courses(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    results = mirror_service.sync_now("999", canvas_get_all=FakeCanvas(), now=NOW)
    assert results == [{"ok": False, "error": "Not a Current course."}]
    results = mirror_service.sync_now("111", canvas_get_all=FakeCanvas(), now=NOW)
    assert results[0]["ok"] is True
    assert results[0]["course_id"] == "111"


# --- routes ------------------------------------------------------------------------

def test_mirror_status_route(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    mirror_service.run_heartbeat_pass(canvas_get_all=FakeCanvas(), now=NOW)
    response = TestClient(app).get("/api/mirror/status")
    payload = response.json()
    assert payload["ok"] is True and payload["enabled"] is True
    course = payload["courses"][0]
    assert course["course_id"] == "111"
    assert course["passes"]["full"]["state"] == "current"
    assert course["watermarks"]["submitted_since"] == "2026-07-16T11:50:00Z"


def test_mirror_sync_now_route(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(mirror_service, "_canvas_get_all", FakeCanvas())
    response = TestClient(app).post("/api/mirror/sync-now", data={"course_id": "111"})
    payload = response.json()
    assert payload["ok"] is True
    assert payload["results"][0]["pass"] == "delta"


# --- write-through notify -------------------------------------------------------------

def test_notify_course_changed_runs_a_delta_after_delay(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    ran = []
    monkeypatch.setattr(mirror_service.sync, "delta_pass",
                        lambda cid, *, canvas_get_all, now=None: ran.append(cid) or {"ok": True})
    timer = mirror_service.notify_course_changed("111", delay_seconds=0.01)
    timer.join(timeout=5)
    assert ran == ["111"]


def test_notify_is_a_no_op_when_disabled(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(mirror_service.config, "mirror_enabled", lambda: False)
    ran = []
    monkeypatch.setattr(mirror_service.sync, "delta_pass",
                        lambda *a, **k: ran.append(1) or {"ok": True})
    timer = mirror_service.notify_course_changed("111", delay_seconds=0.01)
    timer.join(timeout=5)
    assert ran == []
