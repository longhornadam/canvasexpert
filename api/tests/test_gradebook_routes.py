"""Focused route tests for the split Gradebook backend."""

import json

from fastapi.testclient import TestClient

from api.webui.server import app
import api.webui.routes.gradebook as gradebook
import api.webui.routes.gradebook_curves as gradebook_curves
import api.webui.routes.gradebook_snapshot as gradebook_snapshot

client = TestClient(app)


def test_gradebook_facade_reexports_snapshot_route():
    assert gradebook.api_gradebook is gradebook_snapshot.api_gradebook
    assert gradebook.router is not None
    assert gradebook._sweep_compute is not None


def test_gradebook_snapshot_route_aggregates_mocked_canvas_data(monkeypatch):
    monkeypatch.setattr(
        gradebook_snapshot,
        "_course_students",
        lambda course_id: ([{
            "id": 1,
            "name": "Learner One",
            "sortable_name": "One, Learner",
        }, {
            "id": 2,
            "name": "Learner Two",
            "sortable_name": "Two, Learner",
        }], None),
    )
    monkeypatch.setattr(
        gradebook_snapshot,
        "_course_assignments",
        lambda course_id: ([{
            "id": 10,
            "name": "Quiz 1",
            "due_at": "2026-07-01T23:59:00Z",
            "points_possible": 10,
            "html_url": "https://example.invalid/quiz-1",
            "published": True,
        }, {
            "id": 11,
            "name": "Hidden draft",
            "published": False,
        }], None),
    )
    monkeypatch.setattr(
        gradebook_snapshot,
        "_course_submissions",
        lambda course_id: ([{
            "assignment_id": 10,
            "user_id": 1,
            "workflow_state": "graded",
            "score": 9,
            "submitted_at": "2026-07-01T20:00:00Z",
        }, {
            "assignment_id": 10,
            "user_id": 2,
            "workflow_state": "submitted",
            "submitted_at": "2026-07-01T21:00:00Z",
        }], None),
    )

    resp = client.get("/api/gradebook?course_id=42")
    assert resp.status_code == 200
    data = resp.json()

    assert data["ok"] is True
    assert data["class_avg"] == 90.0
    assert data["student_count"] == 2
    assert data["total_missing"] == 0
    assert data["total_ungraded"] == 1
    assert data["assignments"] == [{
        "id": "10",
        "name": "Quiz 1",
        "due_at": "2026-07-01",
        "points": 10,
        "html_url": "https://example.invalid/quiz-1",
        "submitted": 2,
        "graded": 1,
        "missing": 0,
        "late": 0,
        "avg_pct": 90,
    }]
    assert data["students"] == [
        {"name": "One, Learner", "missing": 0, "late": 0, "ungraded": 0, "pct": 90.0},
        {"name": "Two, Learner", "missing": 0, "late": 0, "ungraded": 1, "pct": None},
    ]


def test_curve_list_and_revert_route_shapes_remain_compatible(monkeypatch):
    event = {
        "id": "curve-opaque-1",
        "course_id": "course-opaque-1",
        "assignment_id": "assignment-opaque-1",
        "assignment_name": "Synthetic Assignment",
        "curve_type": "flat_bump",
        "curve_settings": {"bump": 1},
        "applied_at": "2026-07-11T12:00:00",
        "reverted": False,
        "students": [{
            "user_id": "student-opaque-1",
            "student_name": "Synthetic Learner",
            "original_score": 1,
            "curved_score": 2,
        }],
    }
    monkeypatch.setattr(gradebook_curves, "_load_curve_events", lambda: [event.copy()])

    listed = gradebook_curves.list_curve_events("course-opaque-1")
    assert json.loads(listed.body) == {
        "ok": True,
        "events": [{key: value for key, value in event.items() if key != "students"}],
    }

    sent = []
    saved = []
    monkeypatch.setattr(gradebook_curves, "_canvas_get", lambda *_: ({"score": 2}, None))
    monkeypatch.setattr(
        gradebook_curves, "_canvas_send",
        lambda method, url, payload: (sent.append((method, url, payload)) or ({}, None)),
    )
    monkeypatch.setattr(
        gradebook_curves, "_save_curve_events",
        lambda events: saved.append(events),
    )

    reverted = gradebook_curves.revert_curve(
        "curve-opaque-1", "course-opaque-1", "[]")
    body = json.loads(reverted.body)
    assert body["ok"] is True
    assert body["results"][0]["reverted_to"] == 1
    assert sent[0][0] == "PUT"
    assert sent[0][1].endswith("/courses/course-opaque-1/assignments/assignment-opaque-1/submissions/student-opaque-1")
    assert saved[0][0]["reverted"] is True
