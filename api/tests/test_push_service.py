from __future__ import annotations

import json

from api.webui import push_service
from api.webui.routes import push as push_routes


def test_push_assignment_returns_assignment_id(monkeypatch):
    calls = []

    def fake_canvas_send(method, path, payload, timeout=30):
        calls.append((method, path, payload))
        return {
            "id": 12345,
            "name": payload["assignment"]["name"],
            "html_url": "https://canvas.invalid/courses/42/assignments/12345",
        }, None

    monkeypatch.setattr(push_service, "_canvas_send", fake_canvas_send)

    result = push_service._push_assignment("42", {"name": "Essay 1", "submission_types": ["online_text_entry"]}, [])

    assert result.ok is True
    assert result.assignment_id == "12345"
    assert calls[0][1] == "/api/v1/courses/42/assignments"


def test_push_quick_returns_assignment_id(monkeypatch):
    def fake_canvas_send(method, path, payload, timeout=30):
        return {
            "id": 24680,
            "name": payload["assignment"]["name"],
            "html_url": "https://canvas.invalid/courses/42/assignments/24680",
        }, None

    monkeypatch.setattr(push_service, "_canvas_send", fake_canvas_send)

    result = push_service._push_quick("42", {"name": "Exit Ticket", "submission_type": "online_text_entry"}, [])

    assert result.ok is True
    assert result.assignment_id == "24680"


def test_assignmentforge_content_push_uses_af_pusher_and_returns_assignment_id(monkeypatch):
    fake_assignment = {
        "version": "1.0-json",
        "type": "ASSIGNMENT",
        "title": "Essay 1",
        "description": "<p>Prompt</p>",
        "points": 10,
        "submission": {"types": ["online_text_entry"]},
    }

    monkeypatch.setattr(push_service.af, "parse_file", lambda path: (fake_assignment, []))
    monkeypatch.setattr(push_service.af, "tier_payloads", lambda data: [{"title": data["title"], "description": data["description"], "group": None}])
    monkeypatch.setattr(push_service.af, "submission_fields", lambda data: {"submission_types": ["online_text_entry"]})

    def fake_canvas_send(method, path, payload, timeout=30):
        return {
            "id": 67890,
            "name": payload["assignment"]["name"],
            "html_url": "https://canvas.invalid/courses/42/assignments/67890",
        }, None

    monkeypatch.setattr(push_service, "_canvas_send", fake_canvas_send)

    response = push_routes.api_content_push(
        kind="af",
        courses=json.dumps([{ "id": "42", "name": "Period 1" }]),
        payload=json.dumps({"path": "fake.assignmentforge.json"}),
    )
    data = json.loads(response.body)

    assert data["ok"] is True
    assert data["results"][0]["assignment_id"] == "67890"
    assert data["results"][0]["title"] == "Essay 1"


def test_assignmentforge_tiers_fail_closed_until_override_wiring_exists(monkeypatch):
    fake_assignment = {
        "version": "1.0-json",
        "type": "ASSIGNMENT",
        "title": "Tiered Essay",
        "description": "<p>Prompt</p>",
        "submission": {"types": ["online_text_entry"]},
        "tiers": [{"label": "Support", "group": "Blue"}],
    }

    monkeypatch.setattr(push_service.af, "parse_file", lambda path: (fake_assignment, []))

    result = push_service._push_assignmentforge("42", {"path": "fake.assignmentforge.json"}, [])

    assert result.ok is False
    assert "group override" in result.error


def test_assignmentforge_rubric_path_fails_closed_until_wired(monkeypatch):
    fake_assignment = {
        "version": "1.0-json",
        "type": "ASSIGNMENT",
        "title": "Essay 1",
        "description": "<p>Prompt</p>",
        "submission": {"types": ["online_text_entry"]},
    }

    monkeypatch.setattr(push_service.af, "parse_file", lambda path: (fake_assignment, []))

    result = push_service._push_assignmentforge(
        "42",
        {"path": "fake.assignmentforge.json", "rubric_path": "rubric.txt"},
        [],
    )

    assert result.ok is False
    assert "rubric attachment" in result.error
