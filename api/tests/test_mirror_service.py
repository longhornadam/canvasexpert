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
        if path == "/api/v1/courses/111":
            return {"workflow_state": "available", "concluded": False}, None
        if path.endswith("/enrollments"):
            return [{"enrollment_state": "active"}], None
        if path.endswith("/assignments"):
            return [{"id": 700010, "name": "Essay 1", "published": True}], None
        if path.endswith("/users"):
            return [{"id": 900001, "name": "Learner One"}], None
        if path.endswith("/sections"):
            return [], None
        if path.endswith("/students/submissions"):
            return [], None
        raise AssertionError(f"unexpected path {path}")

    def complete(self, path, params=None, timeout=30):
        """Explicit complete-collection receipt for assignment membership."""
        rows, error = self(path, params, timeout)
        return rows, error, error is None


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
    summaries = mirror_service.run_heartbeat_pass(
        canvas_get=canvas, canvas_get_all=canvas, canvas_get_all_complete=canvas.complete, now=NOW)
    assert [(s["course_id"], s["pass"], s["ok"]) for s in summaries] == [("111", "full", True)]
    assert store.read_sync("111")["passes"]["full"]["state"] == "current"


def test_heartbeat_steady_state_runs_delta_only(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    first = FakeCanvas()
    mirror_service.run_heartbeat_pass(
        canvas_get=first, canvas_get_all=first, canvas_get_all_complete=first.complete, now=NOW)
    second = FakeCanvas()
    summaries = mirror_service.run_heartbeat_pass(
        canvas_get=second, canvas_get_all=second, canvas_get_all_complete=second.complete,
        now="2026-07-16T12:15:00Z")
    assert [s["pass"] for s in summaries] == ["delta"]


def test_heartbeat_refreshes_context_first_and_then_daily_only(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    first = FakeCanvas()
    mirror_service.run_heartbeat_pass(
        canvas_get=first, canvas_get_all=first, canvas_get_all_complete=first.complete, now=NOW)
    assert first.calls[:2] == ["/api/v1/courses/111", "/api/v1/courses/111/enrollments"]

    warm = FakeCanvas()
    mirror_service.run_heartbeat_pass(canvas_get=warm, canvas_get_all=warm,
                                      canvas_get_all_complete=warm.complete,
                                      now="2026-07-16T12:15:00Z")
    assert "/api/v1/courses/111" not in warm.calls
    assert "/api/v1/courses/111/enrollments" not in warm.calls

    daily = FakeCanvas()
    mirror_service.run_heartbeat_pass(canvas_get=daily, canvas_get_all=daily,
                                      canvas_get_all_complete=daily.complete,
                                      now="2026-07-17T12:01:00Z")
    assert daily.calls[:2] == ["/api/v1/courses/111", "/api/v1/courses/111/enrollments"]


def test_concluded_warm_heartbeat_suppresses_delta_roster_and_new_quiz(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    store.record_course_context(
        "111", ok=True, attempted_at=NOW, lifecycle="concluded",
        course_workflow_state="completed", course_concluded=True,
        enrollment_states=["completed"])
    store.record_pass("111", "full", ok=True, attempted_at="2026-07-16T11:00:00Z")
    store.record_pass("111", "roster", ok=True, attempted_at="2026-07-16T11:00:00Z")

    def no_canvas_call(*args, **kwargs):
        raise AssertionError("concluded warm heartbeat must make no Canvas call")

    assert mirror_service.run_heartbeat_pass(
        canvas_get=no_canvas_call, canvas_get_all=no_canvas_call,
        canvas_get_all_complete=no_canvas_call, now=NOW) == []


def test_concluded_daily_full_keeps_core_reconcile_and_skips_new_quiz(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    store.record_course_context(
        "111", ok=True, attempted_at=NOW, lifecycle="concluded",
        course_workflow_state="completed", course_concluded=True,
        enrollment_states=["completed"])
    store.record_pass("111", "full", ok=True, attempted_at="2026-07-15T11:00:00Z")
    calls = []

    def core_only(path, params=None, timeout=30):
        calls.append(path)
        if "/api/quiz/v1/" in path:
            raise AssertionError("concluded daily full must skip New Quiz metadata")
        if path.endswith("/assignments"):
            return [{"id": 700099, "name": "New Quiz", "published": True,
                     "is_quiz_lti_assignment": True}], None
        if path.endswith("/users"):
            return [{"id": 900001, "name": "Synthetic Learner"}], None
        if path.endswith("/sections") or path.endswith("/students/submissions"):
            return [], None
        raise AssertionError(path)

    def core_only_complete(path, params=None, timeout=30):
        rows, error = core_only(path, params, timeout)
        return rows, error, error is None

    result = mirror_service.run_heartbeat_pass(
        canvas_get=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("context is fresh")),
        canvas_get_all=core_only, canvas_get_all_complete=core_only_complete, now=NOW)
    assert [(entry["pass"], entry["ok"]) for entry in result] == [("full", True)]
    assert result[0]["new_quizzes"]["state"] == "skipped_lifecycle"
    assert result[0]["new_quizzes"]["skipped_lifecycle"] is True
    assert all("/api/quiz/v1/" not in path for path in calls)


def test_unknown_context_keeps_current_heartbeat_cadence(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)

    class UnknownLifecycleCanvas(FakeCanvas):
        def __call__(self, path, params=None, timeout=30):
            if path.endswith("/enrollments"):
                self.calls.append(path)
                return [], None
            return super().__call__(path, params, timeout)

    first = UnknownLifecycleCanvas()
    first_result = mirror_service.run_heartbeat_pass(
        canvas_get=first, canvas_get_all=first, canvas_get_all_complete=first.complete, now=NOW)
    assert [entry["pass"] for entry in first_result] == ["full"]
    assert store.read_course_context("111")["lifecycle"] == "unknown"
    warm = UnknownLifecycleCanvas()
    warm_result = mirror_service.run_heartbeat_pass(
        canvas_get=warm, canvas_get_all=warm, canvas_get_all_complete=warm.complete,
        now="2026-07-16T12:15:00Z")
    assert [entry["pass"] for entry in warm_result] == ["delta"]


def test_heartbeat_gates_on_token_flag_and_workspace(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(mirror_service.config, "token_is_set", lambda: False)
    first = FakeCanvas()
    assert mirror_service.run_heartbeat_pass(
        canvas_get=first, canvas_get_all=first, canvas_get_all_complete=first.complete, now=NOW) == []

    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(mirror_service.config, "mirror_enabled", lambda: False)
    second = FakeCanvas()
    assert mirror_service.run_heartbeat_pass(
        canvas_get=second, canvas_get_all=second, canvas_get_all_complete=second.complete, now=NOW) == []

    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(workspace, "workspace_root", lambda: None)
    third = FakeCanvas()
    assert mirror_service.run_heartbeat_pass(
        canvas_get=third, canvas_get_all=third, canvas_get_all_complete=third.complete, now=NOW) == []


def test_heartbeat_survives_a_course_that_raises(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path,
               courses=({"id": "111"}, {"id": "222"}))

    def exploding(path, params=None, timeout=30):
        if "/222/" in path:
            raise RuntimeError("boom")
        return FakeCanvas()(path, params, timeout)

    def exploding_complete(path, params=None, timeout=30):
        rows, error = exploding(path, params, timeout)
        return rows, error, error is None

    summaries = mirror_service.run_heartbeat_pass(
        canvas_get=exploding, canvas_get_all=exploding,
        canvas_get_all_complete=exploding_complete, now=NOW)
    by_course = {s["course_id"]: s for s in summaries}
    assert by_course["111"]["ok"] is True
    assert by_course["222"]["ok"] is False


def test_heartbeat_and_manual_sync_thread_the_complete_assignment_seam(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    canvas = FakeCanvas()
    receipt = lambda *args, **kwargs: ([], None, True)
    heartbeat_calls = []
    manual_calls = []
    monkeypatch.setitem(
        mirror_service._PASS_RUNNERS, "full",
        lambda cid, **kwargs: heartbeat_calls.append((cid, kwargs)) or {"ok": True},
    )
    monkeypatch.setattr(
        mirror_service.sync, "delta_pass",
        lambda cid, **kwargs: manual_calls.append((cid, kwargs)) or {"ok": True},
    )

    mirror_service.run_heartbeat_pass(
        canvas_get=canvas, canvas_get_all=canvas,
        canvas_get_all_complete=receipt, now=NOW)
    mirror_service.sync_now(
        "111", canvas_get=canvas, canvas_get_all=canvas,
        canvas_get_all_complete=receipt, now=NOW)

    assert heartbeat_calls[0][1]["canvas_get_all_complete"] is receipt
    assert manual_calls[0][1]["canvas_get_all_complete"] is receipt


# --- sync_now -------------------------------------------------------------------

def test_sync_now_scopes_to_current_courses(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    ignored = FakeCanvas()
    results = mirror_service.sync_now(
        "999", canvas_get=ignored, canvas_get_all=ignored,
        canvas_get_all_complete=ignored.complete, now=NOW)
    assert results == [{"ok": False, "error": "Not a Current course."}]
    canvas = FakeCanvas()
    results = mirror_service.sync_now(
        "111", canvas_get=canvas, canvas_get_all=canvas,
        canvas_get_all_complete=canvas.complete, now=NOW)
    assert results[0]["ok"] is True
    assert results[0]["course_id"] == "111"


def test_sync_now_bypasses_new_quiz_capability_cooldown_the_heartbeat_never_does(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    quiz_calls = []

    class NewQuizCanvas:
        def __call__(self, path, params=None, timeout=30):
            if path == "/api/v1/courses/111":
                return {"workflow_state": "available", "concluded": False}, None
            if path.endswith("/enrollments"):
                return [{"enrollment_state": "active"}], None
            if "/quizzes/" in path:
                quiz_calls.append(path)
            if path.endswith("/assignments"):
                return [{"id": 700099, "name": "New Quiz",
                        "is_quiz_lti_assignment": True, "updated_at": ""}], None
            if path.endswith("/users"):
                return [{"id": 900001, "name": "Learner One"}], None
            if path.endswith("/sections") or path.endswith("/students/submissions"):
                return [], None
            if path.endswith("/quizzes/700099"):
                return [{"id": "700099", "title": "New Quiz"}], None
            if path.endswith("/quizzes/700099/items"):
                return [], None
            raise AssertionError(f"unexpected path {path}")

        complete = FakeCanvas.complete

    # Seed the course as restricted, with a far-future cooldown, before any
    # sync has ever run — so the first heartbeat sees an already-open circuit.
    store.write_new_quiz_capability(
        "111", capability="restricted", last_probe_at=NOW,
        retry_after="2099-01-01T00:00:00Z", evidence_category="forbidden",
        consecutive_failures=3)

    # The heartbeat (first-run backfill) must still skip the New Quiz
    # fan-out entirely — it never bypasses the cooldown.
    heartbeat = NewQuizCanvas()
    mirror_service.run_heartbeat_pass(
        canvas_get=heartbeat, canvas_get_all=heartbeat,
        canvas_get_all_complete=heartbeat.complete, now=NOW)
    assert quiz_calls == []
    assert store.read_new_quiz_capability("111")["capability"] == "restricted"

    # Manual sync now ignores the cooldown entirely and probes the quiz.
    manual = NewQuizCanvas()
    results = mirror_service.sync_now("111", canvas_get=manual, canvas_get_all=manual,
                                      canvas_get_all_complete=manual.complete,
                                      now="2026-07-16T12:20:00Z")
    assert results[0]["ok"] is True
    assert "/api/quiz/v1/courses/111/quizzes/700099" in quiz_calls
    assert store.read_new_quiz_capability("111")["capability"] == "supported"


def test_manual_sync_probes_new_quiz_even_when_lifecycle_is_concluded(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    quiz_calls = []

    class ConcludedCanvas:
        def __call__(self, path, params=None, timeout=30):
            if path == "/api/v1/courses/111":
                return {"workflow_state": "completed", "concluded": True}, None
            if path.endswith("/enrollments"):
                return [{"enrollment_state": "completed"}], None
            if path.endswith("/assignments"):
                return [{"id": 700099, "name": "New Quiz", "published": True,
                         "is_quiz_lti_assignment": True, "updated_at": ""}], None
            if path.endswith("/users"):
                return [{"id": 900001, "name": "Synthetic Learner"}], None
            if path.endswith("/sections") or path.endswith("/students/submissions"):
                return [], None
            if "/api/quiz/v1/" in path:
                quiz_calls.append(path)
                if path.endswith("/items"):
                    return [], None
                return [{"id": "700099", "title": "New Quiz"}], None
            raise AssertionError(path)

        complete = FakeCanvas.complete

    canvas = ConcludedCanvas()
    results = mirror_service.sync_now(
        "111", canvas_get=canvas, canvas_get_all=canvas,
        canvas_get_all_complete=canvas.complete, now=NOW)
    assert results[0]["ok"] is True
    assert store.read_course_context("111")["lifecycle"] == "concluded"
    assert "/api/quiz/v1/courses/111/quizzes/700099" in quiz_calls


# --- routes ------------------------------------------------------------------------

def test_mirror_status_route(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    canvas = FakeCanvas()
    mirror_service.run_heartbeat_pass(
        canvas_get=canvas, canvas_get_all=canvas, canvas_get_all_complete=canvas.complete, now=NOW)
    response = TestClient(app).get("/api/mirror/status")
    payload = response.json()
    assert payload["ok"] is True and payload["enabled"] is True
    course = payload["courses"][0]
    assert course["course_id"] == "111"
    assert course["passes"]["full"]["state"] == "current"
    assert course["watermarks"]["submitted_since"] == "2026-07-16T11:50:00Z"
    assert course["context"]["lifecycle"] == "current"
    assert set(course["context"]) == {
        "schema_version", "course_id", "state", "last_success_at", "last_attempt_at",
        "error_code", "lifecycle", "course_workflow_state", "course_concluded",
        "course_end_at", "term_end_at", "enrollment_states",
    }


def test_mirror_sync_now_route(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    canvas = FakeCanvas()
    monkeypatch.setattr(mirror_service, "_canvas_get_all", canvas)
    monkeypatch.setattr(mirror_service, "_canvas_get_all_complete", canvas.complete)
    monkeypatch.setattr(mirror_service, "_canvas_get", canvas)
    response = TestClient(app).post("/api/mirror/sync-now", data={"course_id": "111"})
    payload = response.json()
    assert payload["ok"] is True
    assert payload["results"][0]["pass"] == "delta"


# --- background findings refresh ------------------------------------------------------

def test_refresh_work_findings_merges_when_configured(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    from api.work_registry import discovery
    merged = []
    monkeypatch.setattr(discovery, "scan_active_courses", lambda: {"ok": True, "courses": {}})
    monkeypatch.setattr(discovery, "merge_into_registry", lambda result: merged.append(result) or {"ok": True})
    mirror_service.refresh_work_findings()
    assert merged == [{"ok": True, "courses": {}}]


def test_refresh_work_findings_skips_partial_scan(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    from api.work_registry import discovery
    merged = []
    monkeypatch.setattr(discovery, "scan_active_courses", lambda: {"ok": False})
    monkeypatch.setattr(discovery, "merge_into_registry", lambda result: merged.append(result))
    mirror_service.refresh_work_findings()
    assert merged == []


def test_refresh_work_findings_gated_off_when_disabled(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(mirror_service.config, "mirror_enabled", lambda: False)
    from api.work_registry import discovery
    called = []
    monkeypatch.setattr(discovery, "scan_active_courses", lambda: called.append(1) or {"ok": True})
    mirror_service.refresh_work_findings()
    assert called == []


# --- write-through notify -------------------------------------------------------------

def test_notify_course_changed_runs_a_delta_after_delay(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    ran = []
    receipt = lambda *args, **kwargs: ([], None, True)
    monkeypatch.setattr(mirror_service.sync, "delta_pass",
                        lambda cid, *, canvas_get_all, canvas_get_all_complete, now=None:
                        ran.append((cid, canvas_get_all_complete)) or {"ok": True})
    timer = mirror_service.notify_course_changed(
        "111", delay_seconds=0.01, canvas_get_all_complete=receipt)
    timer.join(timeout=5)
    assert ran == [("111", receipt)]


def test_notify_is_a_no_op_when_disabled(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(mirror_service.config, "mirror_enabled", lambda: False)
    ran = []
    monkeypatch.setattr(mirror_service.sync, "delta_pass",
                        lambda *a, **k: ran.append(1) or {"ok": True})
    timer = mirror_service.notify_course_changed("111", delay_seconds=0.01)
    timer.join(timeout=5)
    assert ran == []
