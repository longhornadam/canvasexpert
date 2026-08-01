"""Focused tests for POST /api/extend-due: resolves the requested addition
before any Canvas send, and fails closed on an unconfigured or out-of-range
Calendar instead of silently writing an override computed with weekends
counted as school days.
"""
import pytest
from fastapi.testclient import TestClient

from api.tests.calendar_fixtures import write_school_calendar
from api.webui import school_calendar, workspace
from api.webui.routes import gradebook_extensions
from api.webui.server import app

client = TestClient(app)

SCHEDULE_ID = "bell_schedule_ordinary"


@pytest.fixture(autouse=True)
def isolated_workspace(tmp_path, monkeypatch):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(workspace_root))
    monkeypatch.setattr(
        workspace, "library_folder", lambda name: str(workspace_root / "Library" / name)
    )
    return workspace_root


def _bell_schedule(calendars_dir):
    calendars_dir.mkdir(parents=True, exist_ok=True)
    (calendars_dir / "Bell Schedule - Ordinary.csv").write_text(
        "period_id,start,end\n1,08:00,08:45\n", encoding="utf-8")


def test_extend_due_refuses_when_calendar_is_unconfigured(monkeypatch):
    monkeypatch.setattr(gradebook_extensions, "_canvas_get",
                        lambda path: ({"due_at": "2026-08-19T23:59:00Z"}, None))
    response = client.post("/api/extend-due", data={
        "course_id": "1", "assignment_id": "2",
        "student_ids": "[\"10\"]", "days": "1",
    })
    data = response.json()
    assert data["ok"] is False
    assert data["error"] == school_calendar.CALENDAR_REPAIR_MESSAGE


def test_extend_due_refuses_rather_than_walking_past_coverage(isolated_workspace, monkeypatch):
    calendars = isolated_workspace / "Library" / "Calendars"
    _bell_schedule(calendars)
    write_school_calendar(
        calendars, {"2026-08-17": SCHEDULE_ID, "2026-08-18": SCHEDULE_ID},
        coverage_start="2026-08-17", coverage_end="2026-08-18")
    monkeypatch.setattr(gradebook_extensions, "_canvas_get",
                        lambda path: ({"due_at": "2026-08-18T23:59:00Z"}, None))
    sent = {}
    monkeypatch.setattr(gradebook_extensions, "_canvas_send",
                        lambda *a, **kw: sent.setdefault("called", True) or ({}, None))

    response = client.post("/api/extend-due", data={
        "course_id": "1", "assignment_id": "2",
        "student_ids": "[\"10\"]", "days": "1",
    })
    data = response.json()
    assert data["ok"] is False
    assert "called" not in sent  # never reaches the Canvas write


def test_extend_due_writes_the_computed_school_day_due_date(isolated_workspace, monkeypatch):
    calendars = isolated_workspace / "Library" / "Calendars"
    _bell_schedule(calendars)
    # Every date left out of the map becomes no_school in this fixture, so
    # Aug 20/22/23 stand in for "no-count days" regardless of real weekday.
    write_school_calendar(
        calendars, {"2026-08-19": SCHEDULE_ID, "2026-08-21": SCHEDULE_ID, "2026-08-24": SCHEDULE_ID},
        coverage_start="2026-08-17", coverage_end="2026-08-28")
    monkeypatch.setattr(gradebook_extensions, "_canvas_get",
                        lambda path: ({"due_at": "2026-08-19T23:59:00-05:00"}, None))
    sent = {}

    def _fake_send(method, path, body):
        sent["body"] = body
        return {}, None

    monkeypatch.setattr(gradebook_extensions, "_canvas_send", _fake_send)

    response = client.post("/api/extend-due", data={
        "course_id": "1", "assignment_id": "2",
        "student_ids": "[\"10\"]", "days": "2",
    })
    data = response.json()
    assert data["ok"] is True
    # 08-20 is no-count; the next two school days in the fixture are 08-21 and 08-24.
    assert data["new_due"].startswith("2026-08-24")
    assert sent["body"]["assignment_override"]["due_at"].startswith("2026-08-24")
