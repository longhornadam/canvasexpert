"""HTTP integration tests for the operation prepare/review/apply boundary."""

import pytest
from fastapi.testclient import TestClient

from api.operation_ledger import operations, paths
from api.webui.local_request_guard import csrf_token
from api.webui.server import app


@pytest.fixture
def route_env(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "private_root", lambda: tmp_path / "ledger")
    courses = [
        {"id": 101, "name": "Fictional Algebra"},
        {"id": 202, "name": "Fictional Biology"},
        {"id": 303, "name": "Fictional Literature"},
    ]
    monkeypatch.setattr(
        "api.operation_ledger.adapters.quick_assignment.config.active_courses",
        lambda: courses,
    )
    created = []

    def fake_get(path, params=None, timeout=20):
        if params and "search_term" in params:
            return [], None
        assignment_id = path.rsplit("/", 1)[-1]
        return {"id": assignment_id, "html_url": "https://canvas.invalid/item"}, None

    def fake_send(method, path, payload, timeout=30):
        course_id = path.split("/courses/", 1)[1].split("/", 1)[0]
        created.append(course_id)
        return {
            "id": 8000 + len(created),
            "html_url": "https://canvas.invalid/item",
        }, None

    monkeypatch.setattr(
        "api.operation_ledger.adapters.quick_assignment.canvas_client.canvas_get",
        fake_get,
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.quick_assignment.canvas_client._canvas_send",
        fake_send,
    )
    return TestClient(app, base_url="http://127.0.0.1:8765"), created


def _headers(token=None):
    return {
        "X-CanvasExpert-CSRF": csrf_token() if token is None else token,
        "Origin": "http://127.0.0.1:8765",
    }


def _body(targets=None):
    return {
        "payload": {"name": "Practice Column", "points": 10},
        "targets": targets or [{"course_id": "101"}],
    }


def test_prepare_preserves_selected_target_order(route_env):
    client, created = route_env
    response = client.post(
        "/api/operations/content.quick_assignment/prepare",
        json=_body([{"course_id": "202"}, {"course_id": "101"}]),
        headers=_headers(),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["review_summary"]["target_count"] == 2
    assert [item["course_name"] for item in data["review_summary"]["frozen_reviews"]] == [
        "Fictional Biology", "Fictional Algebra",
    ]
    stored = operations.get_operation(data["operation_id"])
    assert [target["course_id"] for target in stored["targets"]] == ["202", "101"]
    assert created == []


def test_prepare_review_apply_writes_only_selected_targets(route_env, monkeypatch):
    from api import operational_log

    client, created = route_env
    records = []
    monkeypatch.setattr(
        operational_log, "emit",
        lambda *args, **kwargs: records.append((args, kwargs)),
    )
    prepared = client.post(
        "/api/operations/content.quick_assignment/prepare",
        json=_body([{"course_id": "202"}, {"course_id": "101"}]),
        headers=_headers(),
    ).json()
    reviewed = client.post(
        "/api/operation-batches/review",
        json={"operation_ids": [prepared["operation_id"]]},
        headers=_headers(),
    ).json()
    applied = client.post(
        f"/api/operation-batches/{reviewed['batch_id']}/apply",
        json={"review_digest": reviewed["review_digest"]},
        headers=_headers(),
    )
    assert applied.status_code == 200
    assert applied.json()["status"] == "applied"
    assert created == ["202", "101"]
    assert any(args == ("operation_ledger.write", "ok") for args, _ in records)
    apply_records = [item for item in records if item[0] == ("operation_ledger.apply", "ok")]
    assert len(apply_records) == 1
    assert apply_records[0][1]["count"] == 2
    assert set(apply_records[0][1]) == {"duration_ms", "count", "error_class"}


@pytest.mark.parametrize("body", [
    None,
    {},
    {"payload": [], "targets": [{"course_id": "101"}]},
    {"payload": {}, "targets": None},
    {"payload": {}, "targets": []},
    {"payload": {}, "targets": {}},
    {"payload": {}, "targets": ["101"]},
    {"payload": {}, "targets": [{"course_id": " "}]},
    {"payload": {}, "targets": [{"course_id": "101"}, {"course_id": 101}]},
    {"payload": {"name": "Practice"}, "targets": [{"course_id": "999"}]},
])
def test_invalid_prepare_envelopes_create_nothing(route_env, body):
    client, created = route_env
    response = client.post(
        "/api/operations/content.quick_assignment/prepare",
        json=body,
        headers=_headers(),
    )
    assert response.status_code == 400
    assert operations.list_operations() == []
    assert created == []


def test_malformed_json_and_invalid_csrf_are_rejected(route_env):
    client, created = route_env
    malformed = client.post(
        "/api/operations/content.quick_assignment/prepare",
        content="{broken",
        headers={**_headers(), "Content-Type": "application/json"},
    )
    assert malformed.status_code == 400
    forbidden = client.post(
        "/api/operations/content.quick_assignment/prepare",
        json=_body(),
        headers=_headers("wrong"),
    )
    assert forbidden.status_code == 403
    assert operations.list_operations() == []
    assert created == []


def test_course_expert_page_renders_csrf(route_env, monkeypatch):
    client, _ = route_env
    monkeypatch.setattr("api.webui.server.config.token_is_set", lambda: True)
    monkeypatch.setattr("api.webui.server.config.get_canvas_base", lambda: "https://canvas.invalid")
    monkeypatch.setattr("api.webui.routes.pages.config.token_is_set", lambda: True)
    monkeypatch.setattr("api.webui.routes.pages.config.get_canvas_base", lambda: "https://canvas.invalid")
    monkeypatch.setattr("api.webui.routes.pages.config.active_courses", lambda: [])
    monkeypatch.setattr("api.webui.routes.pages.list_ai_ta_files", lambda: [])
    monkeypatch.setattr("api.webui.routes.pages.list_assignment_files", lambda: [])
    monkeypatch.setattr("api.webui.routes.pages.list_page_files", lambda: [])
    monkeypatch.setattr("api.webui.routes.pages.list_quiz_files", lambda: [])
    for path in (
        "/course-expert",
    ):
        response = client.get(path, headers={"Accept": "text/html"})
        assert response.status_code == 200, path
        marker = f'name="canvasexpert-csrf-token" content="{csrf_token()}"'
        assert response.text.count(marker) == 1, path
        assert response.text.index(marker) < response.text.index("/static/push/core.js"), path


# ── Operation status polling ─────────────────────────────────────────────

def test_status_unknown_operation_returns_404(route_env):
    client, _ = route_env
    response = client.get("/api/operations/op-nonexistent/status")
    assert response.status_code == 404


def test_status_returns_target_and_step_states(route_env):
    client, _ = route_env
    # Create an operation
    prepared = client.post(
        "/api/operations/content.quick_assignment/prepare",
        json={"payload": {"name": "Practice", "points": 10},
              "targets": [{"course_id": "101"}]},
        headers=_headers(),
    ).json()
    op_id = prepared["operation_id"]

    # Check status before review
    status = client.get(f"/api/operations/{op_id}/status").json()
    assert status["operation_id"] == op_id
    assert status["kind"] == "content.quick_assignment"
    assert status["status"] == "prepared"
    assert len(status["targets"]) == 1
    assert "target_key" in status["targets"][0]
    assert "state" in status["targets"][0]
    assert isinstance(status["targets"][0]["steps"], list)

    # Review and apply
    reviewed = client.post(
        "/api/operation-batches/review",
        json={"operation_ids": [op_id]},
        headers=_headers(),
    ).json()
    applied = client.post(
        f"/api/operation-batches/{reviewed['batch_id']}/apply",
        json={"review_digest": reviewed["review_digest"]},
        headers=_headers(),
    )
    assert applied.status_code == 200

    # Check status after apply
    status2 = client.get(f"/api/operations/{op_id}/status").json()
    assert status2["status"] in ("applied", "applying")
    assert len(status2["targets"]) == 1


def test_status_contains_no_pii(route_env):
    """Verify the status endpoint returns no course IDs, object IDs, URLs, or diagnostics."""
    client, _ = route_env
    prepared = client.post(
        "/api/operations/content.quick_assignment/prepare",
        json={"payload": {"name": "Test", "points": 5},
              "targets": [{"course_id": "101"}]},
        headers=_headers(),
    ).json()
    op_id = prepared["operation_id"]
    status = client.get(f"/api/operations/{op_id}/status").json()

    body = client.get(f"/api/operations/{op_id}/status").content.decode()
    # No course IDs
    assert "101" not in body
    assert "8000" not in body  # no returned object IDs
    assert "canvas.invalid" not in body  # no URLs
    assert "diagnostic" not in body.lower()  # no diagnostics
    assert "canvas_error" not in body.lower()
    # No payload fields
    assert "Practice" not in body
    assert "payload" not in body.lower()
