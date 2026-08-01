"""HTTP end-to-end tests: sweep apply goes through the operation ledger.

Slice 00b hardening: the direct-PUT ``/api/sweep/apply`` route is gone. The
only way to write ``seconds_late_override`` from the browser is the generic
prepare → review → apply operation flow for kind ``gradebook.sweep``, whose
adapter recomputes the write set from authoritative Canvas state. These tests
prove browser-submitted entries can never become the write set.

All Canvas data below is fictional.
"""
import copy
import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from api.operation_ledger import paths
from api.webui.local_request_guard import csrf_token
from api.webui.server import app


def _weekend_dates(start="2026-01-01", end="2026-12-31"):
    """Stand-in for the canonical calendar's generated weekend no-school days."""
    cursor = date.fromisoformat(start)
    end_d = date.fromisoformat(end)
    found = set()
    while cursor <= end_d:
        if cursor.weekday() >= 5:
            found.add(cursor.isoformat())
        cursor += timedelta(days=1)
    return found


FAKE_ASSIGNMENTS = [{
    "id": 10, "name": "Fictional Essay", "published": True,
    "due_at": "2026-06-01T23:59:00Z",
}]
# Due Mon 2026-06-01, submitted Wed 2026-06-03 → 2 school days late.
FAKE_SUBMISSIONS = [{
    "assignment_id": 10, "user_id": 1,
    "submitted_at": "2026-06-03T12:00:00Z",
    "workflow_state": "late",
}]
FAKE_STUDENTS = [{"id": 1, "sortable_name": "Fictional, Student"}]
EXPECTED_SECONDS = 2 * 86400


@pytest.fixture
def sweep_env(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "private_root", lambda: tmp_path / "ledger")
    monkeypatch.setattr(
        "api.operation_ledger.adapters.sweep.config.active_courses",
        lambda: [{"id": 101, "name": "Fictional Algebra"}],
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.sweep.school_calendar.resolve_instructional_range",
        lambda date_from, date_to, known_schedule_ids, **kw: {
            "state": "ready", "date_from": date_from, "date_to": date_to,
            "days": {}, "no_count_dates": sorted(_weekend_dates()),
        },
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.sweep.config.get_extra_time",
        lambda course_id: [],
    )
    monkeypatch.setattr(
        "api.webui.routes.gradebook_sweep.config.set_sweep_settings",
        lambda s: None,
    )

    canvas = {
        "assignments": copy.deepcopy(FAKE_ASSIGNMENTS),
        "submissions": copy.deepcopy(FAKE_SUBMISSIONS),
        "students": copy.deepcopy(FAKE_STUDENTS),
    }
    writes = []

    def fake_get_all(path, params=None, timeout=30):
        if "assignments" in path and "submissions" not in path:
            return canvas["assignments"], None
        if "submissions" in path:
            return canvas["submissions"], None
        if "users" in path:
            return canvas["students"], None
        return [], None

    def fake_send(method, path, payload, timeout=30):
        writes.append({"method": method, "path": path, "payload": payload})
        return {"ok": True}, None

    monkeypatch.setattr(
        "api.operation_ledger.adapters.sweep.canvas_client._canvas_get_all",
        fake_get_all,
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.sweep.canvas_client._canvas_send",
        fake_send,
    )
    client = TestClient(app, base_url="http://127.0.0.1:8765")
    return client, canvas, writes


def _headers():
    return {
        "X-CanvasExpert-CSRF": csrf_token(),
        "Origin": "http://127.0.0.1:8765",
    }


def _prepare(client, payload=None):
    return client.post(
        "/api/operations/gradebook.sweep/prepare",
        json={"payload": payload or {"honor_extra_time": True},
              "targets": [{"course_id": "101"}]},
        headers=_headers(),
    )


def _review(client, operation_id):
    return client.post(
        "/api/operation-batches/review",
        json={"operation_ids": [operation_id]},
        headers=_headers(),
    )


def _apply(client, batch_id, review_digest):
    return client.post(
        f"/api/operation-batches/{batch_id}/apply",
        json={"review_digest": review_digest},
        headers=_headers(),
    )


def test_direct_apply_route_is_gone(sweep_env):
    client, _canvas, writes = sweep_env
    response = client.post(
        "/api/sweep/apply",
        data={"course_id": "101",
              "entries": '[{"user_id": 999, "assignment_id": 10, '
                         '"seconds_override": 999999, "school_days": 11}]'},
    )
    assert response.status_code == 404
    assert writes == []


def test_client_authored_entries_cannot_become_the_write_set(sweep_env):
    """A tampered prepare payload smuggling entries must be ignored: the
    adapter recomputes the write set from Canvas state, so the executed PUTs
    match the recomputed values, never the client's."""
    client, _canvas, writes = sweep_env
    tampered_payload = {
        "honor_extra_time": True,
        # Attempted injection — build_payload accepts settings only.
        "entries": [{"user_id": 999, "assignment_id": 77,
                     "seconds_override": 9999999}],
        "seconds_override": 9999999,
    }
    prepared = _prepare(client, tampered_payload)
    assert prepared.status_code == 200
    prep = prepared.json()
    frozen = prep["review_summary"]["frozen_reviews"][0]
    assert frozen["entry_count"] == 1
    assert "entries" not in frozen["settings"]

    reviewed = _review(client, prep["operation_id"]).json()
    applied = _apply(client, reviewed["batch_id"], reviewed["review_digest"])
    assert applied.status_code == 200
    assert applied.json()["status"] == "applied"

    # Exactly the recomputed write, never the client-authored values.
    assert len(writes) == 1
    write = writes[0]
    assert write["method"] == "PUT"
    assert "/courses/101/assignments/10/submissions/1" in write["path"]
    assert write["payload"]["submission"]["seconds_late_override"] == EXPECTED_SECONDS
    blob = str(writes)
    assert "999" not in blob
    assert "77" not in blob


def test_wrong_review_digest_is_rejected(sweep_env):
    client, _canvas, writes = sweep_env
    prep = _prepare(client).json()
    reviewed = _review(client, prep["operation_id"]).json()
    applied = _apply(client, reviewed["batch_id"], "tampered-digest")
    assert applied.status_code == 400
    assert writes == []


def test_drift_between_review_and_apply_blocks_the_write(sweep_env):
    """If Canvas state changes after review, the adapter's drift check blocks
    the target and nothing is written."""
    client, canvas, writes = sweep_env
    prep = _prepare(client).json()
    reviewed = _review(client, prep["operation_id"]).json()

    # Canvas changes between review and apply: a second late submission.
    canvas["submissions"].append({
        "assignment_id": 10, "user_id": 2,
        "submitted_at": "2026-06-04T12:00:00Z",
        "workflow_state": "late",
    })

    applied = _apply(client, reviewed["batch_id"], reviewed["review_digest"])
    assert applied.status_code == 200
    body = applied.json()
    assert body["ok"] is False
    assert body["target_results"][0]["state"] == "blocked"
    assert body["target_results"][0]["error_code"] == "drift_detected"
    assert writes == []


# ── Slice 00c: single compute owner, corrected semantics ─────────────────

# Due Friday, submitted Monday: crosses a weekend → 1 school day late,
# 3 calendar days late, 2 weekend dates excluded from the count.
WEEKEND_ASSIGNMENT = {
    "id": 20, "name": "Weekend Crossing Lab", "published": True,
    "due_at": "2026-06-05T17:00:00Z",
}
WEEKEND_SUBMISSION = {
    "assignment_id": 20, "user_id": 1,
    "submitted_at": "2026-06-08T17:00:00Z",
    "workflow_state": "late",
}


def _preview(client, settings=None):
    return client.post(
        "/api/sweep/preview",
        data={"course_id": "101",
              "settings": json.dumps(settings or {"honor_extra_time": True})},
    )


def test_preview_returns_200_and_counts_weekend_crossing_row(sweep_env):
    """The old skip-on-excluded branch silently dropped this row; the old
    gradebook_service compute crashed (HTTP 500). Now: counted correctly."""
    client, canvas, _writes = sweep_env
    canvas["assignments"][:] = [dict(WEEKEND_ASSIGNMENT)]
    canvas["submissions"][:] = [dict(WEEKEND_SUBMISSION)]
    response = _preview(client)
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert len(body["entries"]) == 1
    entry = body["entries"][0]
    assert entry["school_days"] == 1
    assert entry["seconds_override"] == 86400
    assert entry["canvas_days"] == 3
    assert len(entry["excluded_dates"]) == 2
    assert all("(no-count)" in d for d in entry["excluded_dates"])
    assert body["skipped"] == []


def test_apply_write_set_includes_weekend_crossing_row(sweep_env):
    """Proves the skip-branch removal reaches real writes, not just preview."""
    client, canvas, writes = sweep_env
    canvas["assignments"][:] = [dict(WEEKEND_ASSIGNMENT)]
    canvas["submissions"][:] = [dict(WEEKEND_SUBMISSION)]
    prep = _prepare(client).json()
    reviewed = _review(client, prep["operation_id"]).json()
    applied = _apply(client, reviewed["batch_id"], reviewed["review_digest"]).json()
    assert applied["status"] == "applied"
    assert len(writes) == 1
    assert "/assignments/20/submissions/1" in writes[0]["path"]
    assert writes[0]["payload"]["submission"]["seconds_late_override"] == 86400


def test_date_range_bounds_filter_assignments(sweep_env):
    client, canvas, _writes = sweep_env
    canvas["assignments"][:] = [
        dict(FAKE_ASSIGNMENTS[0]),  # due 2026-06-01
        {"id": 30, "name": "Later Fictional Quiz", "published": True,
         "due_at": "2026-06-15T17:00:00Z"},
    ]
    canvas["submissions"][:] = [
        dict(FAKE_SUBMISSIONS[0]),
        {"assignment_id": 30, "user_id": 1,
         "submitted_at": "2026-06-17T17:00:00Z", "workflow_state": "late"},
    ]
    both = _preview(client).json()
    assert {e["assignment_id"] for e in both["entries"]} == {10, 30}
    lower_bounded = _preview(client, {
        "honor_extra_time": True, "date_from": "2026-06-10",
        "date_to": "2026-06-30"}).json()
    assert {e["assignment_id"] for e in lower_bounded["entries"]} == {30}
    upper_bounded = _preview(client, {
        "honor_extra_time": True, "date_to": "2026-06-10"}).json()
    assert {e["assignment_id"] for e in upper_bounded["entries"]} == {10}


def test_preview_and_apply_agree_on_identical_fixture(sweep_env):
    """Single compute owner: what preview shows is exactly what apply writes."""
    client, canvas, writes = sweep_env
    canvas["assignments"].append(dict(WEEKEND_ASSIGNMENT))
    canvas["submissions"].append(dict(WEEKEND_SUBMISSION))
    preview = _preview(client).json()
    expected = {(e["user_id"], e["assignment_id"], e["seconds_override"])
                for e in preview["entries"]}
    assert len(expected) == 2

    prep = _prepare(client).json()
    reviewed = _review(client, prep["operation_id"]).json()
    applied = _apply(client, reviewed["batch_id"], reviewed["review_digest"]).json()
    assert applied["status"] == "applied"

    written = set()
    for w in writes:
        parts = w["path"].split("/")
        written.add((int(parts[-1]), int(parts[-3]),
                     w["payload"]["submission"]["seconds_late_override"]))
    assert written == expected


def test_extra_time_reduces_or_skips_rows(sweep_env, monkeypatch):
    client, canvas, _writes = sweep_env
    canvas["assignments"][:] = [dict(WEEKEND_ASSIGNMENT)]  # 1 school day late
    canvas["submissions"][:] = [dict(WEEKEND_SUBMISSION)]
    monkeypatch.setattr(
        "api.operation_ledger.adapters.sweep.config.get_extra_time",
        lambda course_id: [{"id": 1, "days": 2}],
    )
    covered = _preview(client).json()
    assert covered["entries"] == []
    assert covered["skipped"][0]["reason"] == "covered by extra time"

    ignored = _preview(client, {"honor_extra_time": False}).json()
    assert len(ignored["entries"]) == 1
    assert ignored["entries"][0]["school_days"] == 1

    # Partial subtraction: 2 school days late minus 1 extra-time day.
    canvas["assignments"][:] = [dict(FAKE_ASSIGNMENTS[0])]
    canvas["submissions"][:] = [dict(FAKE_SUBMISSIONS[0])]
    monkeypatch.setattr(
        "api.operation_ledger.adapters.sweep.config.get_extra_time",
        lambda course_id: [{"id": 1, "days": 1}],
    )
    partial = _preview(client).json()
    assert partial["entries"][0]["school_days"] == 1
    assert partial["entries"][0]["extra_days"] == 1
    assert partial["entries"][0]["seconds_override"] == 86400


def test_per_student_cached_due_date_overrides_class_due(sweep_env):
    """A later per-student due date must reduce computed lateness: the sweep
    resolves due from the submission's cached_due_date over the class due_at.
    Class due Mon 2026-06-01, submitted Wed 2026-06-03 → 2 school days late;
    a per-student override to Tue 2026-06-02 makes it 1 school day late."""
    client, canvas, _writes = sweep_env
    canvas["assignments"][:] = [dict(FAKE_ASSIGNMENTS[0])]
    canvas["submissions"][:] = [dict(FAKE_SUBMISSIONS[0],
                                     cached_due_date="2026-06-02T23:59:00Z")]
    entry = _preview(client).json()["entries"][0]
    assert entry["school_days"] == 1
    assert entry["seconds_override"] == 86400


def test_apply_triggers_write_through_convergence(sweep_env, monkeypatch):
    """A successful sweep apply converges the submission mirror exactly once
    (write-through refresh), keyed to the swept course."""
    client, canvas, _writes = sweep_env
    canvas["assignments"][:] = [dict(WEEKEND_ASSIGNMENT)]
    canvas["submissions"][:] = [dict(WEEKEND_SUBMISSION)]
    import api.webui.mirror_service as mirror_service
    notified = []
    monkeypatch.setattr(mirror_service, "notify_course_changed",
                        lambda course_id, **kw: notified.append(str(course_id)))
    prep = _prepare(client).json()
    reviewed = _review(client, prep["operation_id"]).json()
    applied = _apply(client, reviewed["batch_id"], reviewed["review_digest"]).json()
    assert applied["status"] == "applied"
    assert notified == ["101"]


def test_legacy_sweep_compute_is_deleted():
    import api.webui.gradebook_service as gradebook_service
    import api.webui.routes.gradebook as gradebook_facade
    assert not hasattr(gradebook_service, "_sweep_compute")
    assert not hasattr(gradebook_facade, "_sweep_compute")
