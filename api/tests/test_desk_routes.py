"""Focused route/render contracts for the slice-07 Desk surface."""

from fastapi.testclient import TestClient

from api.webui.server import app
from api.webui.routes import pages
from api.work_registry.providers import finding


def _client():
    return TestClient(app, base_url="http://127.0.0.1:8765")


def _configure(monkeypatch):
    monkeypatch.setattr(pages.config, "token_is_set", lambda: True)
    monkeypatch.setattr(pages.config, "get_canvas_base", lambda: "https://canvas.example.test")
    monkeypatch.setattr(pages.workspace, "workspace_root", lambda: None)
    monkeypatch.setattr(pages.config, "active_courses", lambda: [
        {"id": "course-1", "name": "Course One", "nickname": "Course One", "active": True},
        {"id": "course-2", "name": "Course Two", "nickname": "Course Two", "active": True},
    ])


def test_desk_empty_render_is_local_and_honest(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(pages.work_routes, "_section_jobs", lambda section: [])
    monkeypatch.setattr(pages.receipt_store, "list_receipts", lambda: [])

    response = _client().get("/")

    assert response.status_code == 200
    assert 'class="ce-desk-shell"' in response.text
    assert 'id="desk-course-field"' in response.text
    assert "No open work." in response.text
    assert "No items need review." in response.text
    assert "No prepared operations." in response.text
    assert "No receipts." in response.text
    assert "/api/operations" not in response.text
    assert 'name="canvasexpert-csrf-token"' in response.text


def test_desk_populated_render_uses_registry_and_real_receipt_projection(monkeypatch):
    _configure(monkeypatch)
    job = finding(
        kind="grade.debt",
        course_id="course-1",
        assignment_id="assignment-1",
        counts={"total": 2, "pending": 1, "affected": 1},
        now="2026-07-11T12:00:00+00:00",
        resumable_url="/gradebook",
    )
    receipt = {
        "receipt_id": "receipt-1",
        "kind": "gradebook.sweep",
        "status": "partial",
        "target_count": 1,
        "detail_url": "/api/receipts/receipt-1",
    }
    monkeypatch.setattr(pages.work_routes, "_section_jobs", lambda section: [job])
    monkeypatch.setattr(pages.receipt_store, "list_receipts", lambda: [receipt])

    response = _client().get("/")

    assert response.status_code == 200
    assert "Work needs attention" in response.text
    assert "gradebook.sweep" in response.text
    assert "/api/receipts/receipt-1" in response.text
    assert "Course One" in response.text
