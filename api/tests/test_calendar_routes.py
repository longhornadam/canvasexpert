"""Calendar page API routes: staged year create/replace, date-change preview/
apply, and the no-path-input folder-open action.
"""
import json

import pytest
from fastapi.testclient import TestClient

from api.webui import deps, workspace
from api.webui.server import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_workspace(tmp_path, monkeypatch):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(workspace_root))
    monkeypatch.setattr(
        workspace, "library_folder", lambda name: str(workspace_root / "Library" / name)
    )
    monkeypatch.setattr(workspace, "path_within_workspace", lambda p: True)
    return workspace_root


def _bell_schedule(calendars_dir):
    calendars_dir.mkdir(parents=True, exist_ok=True)
    path = calendars_dir / "Bell Schedule - Ordinary.csv"
    path.write_text("period_id,start,end\n1,08:00,08:45\n", encoding="utf-8")
    return "bell_schedule_ordinary"


def test_get_api_calendar_exposes_no_absolute_paths(isolated_workspace):
    data = client.get("/api/calendar").json()
    assert data["ok"] is True
    assert "path" not in data["teacher_schedule"]
    assert "folders" not in data
    blob = json.dumps(data)
    assert str(isolated_workspace) not in blob


def test_year_preview_is_create_at_base_revision_zero(isolated_workspace):
    calendars = isolated_workspace / "Library" / "Calendars"
    schedule_id = _bell_schedule(calendars)
    response = client.post("/api/calendar/year/preview", data={
        "school_year": "2026-27",
        "coverage_start": "2026-08-17",
        "coverage_end": "2026-08-18",
        "default_schedule_id": schedule_id,
    })
    data = response.json()
    assert data["ok"] is True
    assert data["operation"] == "create"
    assert data["base_revision"] == 0


def test_year_preview_rejects_an_unknown_bell_schedule(isolated_workspace):
    (isolated_workspace / "Library" / "Calendars").mkdir(parents=True, exist_ok=True)
    response = client.post("/api/calendar/year/preview", data={
        "school_year": "2026-27",
        "coverage_start": "2026-08-17",
        "coverage_end": "2026-08-18",
        "default_schedule_id": "not_a_real_schedule",
    })
    data = response.json()
    assert data["ok"] is False
    assert "not currently loaded" in data["problems"][0]


def test_year_preview_then_apply_writes_revision_1(isolated_workspace):
    calendars = isolated_workspace / "Library" / "Calendars"
    schedule_id = _bell_schedule(calendars)
    preview = client.post("/api/calendar/year/preview", data={
        "school_year": "2026-27",
        "coverage_start": "2026-08-17",
        "coverage_end": "2026-08-18",
        "default_schedule_id": schedule_id,
    }).json()
    apply_response = client.post("/api/calendar/year/apply", data={
        "expected_revision": preview["base_revision"],
        "preview": json.dumps({k: v for k, v in preview.items() if k != "ok"}),
    }).json()
    assert apply_response["ok"] is True
    assert apply_response["revision"] == 1


def test_year_apply_refuses_a_stale_preview(isolated_workspace):
    calendars = isolated_workspace / "Library" / "Calendars"
    schedule_id = _bell_schedule(calendars)
    body = {
        "school_year": "2026-27",
        "coverage_start": "2026-08-17",
        "coverage_end": "2026-08-18",
        "default_schedule_id": schedule_id,
    }
    preview = client.post("/api/calendar/year/preview", data=body).json()
    payload = {k: v for k, v in preview.items() if k != "ok"}
    # First apply succeeds and advances the real revision to 1.
    client.post("/api/calendar/year/apply", data={
        "expected_revision": 0, "preview": json.dumps(payload),
    })
    # Re-applying the same (now-stale) preview must be refused, not double-write.
    stale = client.post("/api/calendar/year/apply", data={
        "expected_revision": 0, "preview": json.dumps(payload),
    }).json()
    assert stale["ok"] is False
    assert "stale revision" in stale["problems"][0]


def test_change_preview_rejects_an_unknown_bell_schedule(isolated_workspace):
    calendars = isolated_workspace / "Library" / "Calendars"
    schedule_id = _bell_schedule(calendars)
    preview = client.post("/api/calendar/year/preview", data={
        "school_year": "2026-27", "coverage_start": "2026-08-17",
        "coverage_end": "2026-08-18", "default_schedule_id": schedule_id,
    }).json()
    client.post("/api/calendar/year/apply", data={
        "expected_revision": 0,
        "preview": json.dumps({k: v for k, v in preview.items() if k != "ok"}),
    })

    response = client.post("/api/calendar/change/preview", data={
        "kind": "instructional", "schedule_id": "some_other_schedule",
        "dates": json.dumps(["2026-08-17"]),
    })
    data = response.json()
    assert data["ok"] is False
    assert "not a currently loaded Bell Schedule" in data["problems"][0]


def test_open_calendars_folder_needs_no_path_input(isolated_workspace, monkeypatch):
    calendars = isolated_workspace / "Library" / "Calendars"
    calendars.mkdir(parents=True, exist_ok=True)
    opened = {}

    def _fake_open(path):
        opened["path"] = path

    monkeypatch.setattr("api.webui.routes.calendar._open_in_os", _fake_open)
    response = client.post("/api/calendar/open-folder")
    data = response.json()
    assert data["ok"] is True
    assert opened["path"] == str(calendars)


def test_open_calendars_folder_missing_reports_not_found(isolated_workspace):
    response = client.post("/api/calendar/open-folder")
    data = response.json()
    assert data["ok"] is False


def test_import_academic_csv_expands_multi_day_no_school_labels(isolated_workspace):
    csv_text = (
        "Category,Name,Start Date,End Date\n"
        "Student Day Off,Fall Break,10/10/2027,10/12/2027\n"
        "Academic Period,Quarter 1,08/16/2027,10/15/2027\n"
    )
    response = client.post("/api/calendar/import", data={"content": csv_text})
    data = response.json()
    assert data["ok"] is True
    assert data["date_labels"] == {
        "2027-10-10": "Fall Break",
        "2027-10-11": "Fall Break",
        "2027-10-12": "Fall Break",
    }
    assert data["grading_periods"][0]["code"] == "QUARTER_1"
