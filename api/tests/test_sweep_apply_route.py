"""HTTP end-to-end tests: sweep apply goes through the operation ledger.

Slice 00b hardening: the direct-PUT ``/api/sweep/apply`` route is gone. The
only way to write ``seconds_late_override`` from the browser is the generic
prepare → review → apply operation flow for kind ``gradebook.sweep``, whose
adapter recomputes the write set from authoritative Canvas state. These tests
prove browser-submitted entries can never become the write set.

All Canvas data below is fictional.
"""
import copy

import pytest
from fastapi.testclient import TestClient

from api.operation_ledger import paths
from api.webui.local_request_guard import csrf_token
from api.webui.server import app


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
        "api.operation_ledger.adapters.sweep.config.get_combined_calendar_for_range",
        lambda: {"no_count_dates": []},
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
        json={"payload": payload or {"skip_weekends": True},
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
        "skip_weekends": True,
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
