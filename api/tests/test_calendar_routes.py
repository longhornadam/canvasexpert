"""Calendar page API routes: staged year create/replace, date-change preview/
apply, and the no-path-input folder-open action.
"""
import json
import pathlib

import pytest
from fastapi.testclient import TestClient

from api.platform_services import workspace
from api.webui import deps
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
    path.write_text("period_id,start,end\n1,8:00 AM,8:45 AM\n", encoding="utf-8")
    return "bell_schedule_ordinary"


def test_get_api_calendar_exposes_no_absolute_paths(isolated_workspace):
    data = client.get("/api/calendar").json()
    assert data["ok"] is True
    assert "path" not in data["teacher_schedule"]
    assert "folders" not in data
    blob = json.dumps(data)
    assert str(isolated_workspace) not in blob


def test_calendar_page_prioritizes_teacher_schedule_and_collapses_secondary_surfaces(
    isolated_workspace,
):
    html = client.get("/calendar").text

    assert html.index('id="calendar-teacher-card"') < html.index('id="calendar-readiness-card"')
    assert html.index('id="calendar-readiness-card"') < html.index('id="calendar-change-card"')
    assert html.index('id="calendar-change-card"') < html.index('id="calendar-events-card"')
    assert html.index('id="calendar-events-card"') < html.index('id="calendar-create-card"')
    assert html.index('id="calendar-create-card"') < html.index('id="calendar-bell-card"')
    assert html.index('id="calendar-teacher-card"') < html.index('id="calendar-bell-card"')
    assert "Daily work" in html
    assert html.index("Teacher Schedule") < html.index("Today &amp; upcoming")
    for section_id in ("calendar-events-card", "calendar-create-card", "calendar-bell-card"):
        assert (
            f'<details class="ce-panel ce-calendar-panel ce-calendar-secondary" '
            f'id="{section_id}">'
        ) in html
        assert f'id="{section_id}" open' not in html


def test_calendar_page_disclosure_links_are_wired_to_open_secondary_surfaces():
    js = (pathlib.Path(__file__).resolve().parents[1]
          / "webui" / "static" / "pages" / "calendar.js").read_text(encoding="utf-8")

    assert 'a[href^="#calendar-"]' in js
    assert 'target.open = true' in js
    assert "openHashTarget" in js


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


def test_event_preview_apply_round_trips_game_result_without_real_workspace_write(isolated_workspace):
    calendars = isolated_workspace / "Library" / "Calendars"
    schedule_id = _bell_schedule(calendars)
    year_preview = client.post("/api/calendar/year/preview", data={
        "school_year": "2026-27", "coverage_start": "2026-08-17",
        "coverage_end": "2026-08-18", "default_schedule_id": schedule_id,
    }).json()
    client.post("/api/calendar/year/apply", data={
        "expected_revision": 0,
        "preview": json.dumps({k: v for k, v in year_preview.items() if k != "ok"}),
    })
    event = {"id": "game-1", "kind": "game", "label": "Bobcats", "shape": "date",
             "date": "2026-08-18", "result": "Won 2-1"}
    preview = client.post("/api/calendar/event/preview", data={
        "action": "upsert", "event": json.dumps(event),
    }).json()
    assert preview["ok"] is True
    assert preview["operation"] == "event_change"
    assert preview["after"]["result"] == "Won 2-1"
    applied = client.post("/api/calendar/event/apply", data={
        "expected_revision": preview["base_revision"],
        "preview": json.dumps({k: v for k, v in preview.items() if k != "ok"}),
    }).json()
    assert applied["ok"] is True and applied["revision"] == 2
    assert "events" not in applied
    assert client.get("/api/calendar").json()["events"] == [event]
    assert not (isolated_workspace / "School Calendar.json").exists()


def test_event_delete_preview_apply_round_trips_through_calendar_routes(isolated_workspace):
    calendars = isolated_workspace / "Library" / "Calendars"
    schedule_id = _bell_schedule(calendars)
    year_preview = client.post("/api/calendar/year/preview", data={
        "school_year": "2026-27", "coverage_start": "2026-08-17",
        "coverage_end": "2026-08-18", "default_schedule_id": schedule_id,
    }).json()
    client.post("/api/calendar/year/apply", data={
        "expected_revision": 0,
        "preview": json.dumps({k: v for k, v in year_preview.items() if k != "ok"}),
    })
    event_preview = client.post("/api/calendar/event/preview", data={
        "action": "upsert", "event": json.dumps({
            "id": "game-1", "kind": "game", "label": "Bobcats", "shape": "date",
            "date": "2026-08-18", "result": "Scheduled",
        }),
    }).json()
    client.post("/api/calendar/event/apply", data={
        "expected_revision": event_preview["base_revision"],
        "preview": json.dumps({k: v for k, v in event_preview.items() if k != "ok"}),
    })

    preview = client.post("/api/calendar/event/preview", data={
        "action": "delete", "event_id": "game-1",
    }).json()
    assert preview["ok"] is True
    assert preview["mutation"] == {"action": "delete", "event_id": "game-1"}
    assert preview["after"] is None

    applied = client.post("/api/calendar/event/apply", data={
        "expected_revision": preview["base_revision"],
        "preview": json.dumps({k: v for k, v in preview.items() if k != "ok"}),
    }).json()
    assert applied == {"ok": True, "revision": 3}
    assert client.get("/api/calendar").json()["events"] == []


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
    assert data["notes"] == []


def test_import_academic_csv_reports_skipped_rows_as_notes(isolated_workspace):
    csv_text = (
        "Category,Name,Start Date,End Date\n"
        "Pep Rally,Homecoming,09/25/2027,09/25/2027\n"
        "Holiday,Labor Day,09/06/2027,09/06/2027\n"
    )
    response = client.post("/api/calendar/import", data={"content": csv_text})
    data = response.json()
    assert data["ok"] is True
    assert data["no_school_dates"] == ["2027-09-06"]
    assert data["notes"] == ["row 2: skipped, unrecognized Category 'Pep Rally'"]
    assert "problems" not in data


def test_import_academic_csv_stays_ok_with_notes_when_nothing_parsed(isolated_workspace):
    csv_text = (
        "Category,Name,Start Date,End Date\n"
        "Pep Rally,Homecoming,09/25/2027,09/25/2027\n"
    )
    data = client.post("/api/calendar/import", data={"content": csv_text}).json()
    assert data["ok"] is True
    assert data["no_school_dates"] == [] and data["grading_periods"] == []
    assert isinstance(data["notes"], list) and len(data["notes"]) == 1


def test_year_preview_accepts_the_pages_weekday_and_grading_period_payload(isolated_workspace):
    """The Calendar page sends weekday_schedules and grading_periods as JSON
    strings with string weekday keys. Preview must take that shape as-is."""
    calendars = isolated_workspace / "Library" / "Calendars"
    schedule_id = _bell_schedule(calendars)
    friday = calendars / "Bell Schedule - Friday.csv"
    friday.write_text("period_id,start,end\n1,8:00 AM,8:40 AM\n", encoding="utf-8")
    preview = client.post("/api/calendar/year/preview", data={
        "school_year": "2026-27",
        "coverage_start": "2026-08-17",
        "coverage_end": "2026-08-21",
        "default_schedule_id": schedule_id,
        "weekday_schedules": json.dumps({"4": "bell_schedule_friday"}),
        "grading_periods": json.dumps([
            {"code": "T1", "name": "Term 1", "start": "2026-08-17", "end": "2026-08-21"},
        ]),
    }).json()
    assert preview["ok"] is True, preview
    assert preview["grading_period_count"] == 1
    days = preview["mutation"]["weekday_schedules"]
    assert days == {"4": "bell_schedule_friday"}


def test_get_api_calendar_returns_grading_periods_for_the_editor(isolated_workspace):
    """The page prefills its grading-period editor from this key, so a
    Create/Replace that never opens the editor cannot silently drop periods."""
    calendars = isolated_workspace / "Library" / "Calendars"
    schedule_id = _bell_schedule(calendars)
    periods = [{"code": "T1", "name": "Term 1",
                "start": "2026-08-17", "end": "2026-08-18"}]
    preview = client.post("/api/calendar/year/preview", data={
        "school_year": "2026-27",
        "coverage_start": "2026-08-17",
        "coverage_end": "2026-08-18",
        "default_schedule_id": schedule_id,
        "grading_periods": json.dumps(periods),
    }).json()
    client.post("/api/calendar/year/apply", data={
        "expected_revision": preview["base_revision"],
        "preview": json.dumps({k: v for k, v in preview.items() if k != "ok"}),
    })
    data = client.get("/api/calendar").json()
    assert data["grading_periods"] == periods


def test_academic_calendar_guide_is_downloadable_for_pasting_into_an_assistant():
    """The Create/replace surface leads with this guide, so the download name it
    links must resolve to the canonical authoring file."""
    response = client.get("/api/download-contract", params={"name": "AcademicCalendar"})
    assert response.status_code == 200, response.text
    assert "attachment" in response.headers.get("content-disposition", "")
    assert response.text.lstrip().startswith("ACADEMIC CALENDAR AUTHORING")


def test_calendar_js_guide_url_matches_the_registered_download_name():
    """calendar.js fetches the guide by download name to copy it. A rename in
    the route map would break the Copy control with no error anywhere, so pin
    the two together."""
    from api.webui.routes import library

    js = (pathlib.Path(__file__).resolve().parents[1]
          / "webui" / "static" / "pages" / "calendar.js").read_text(encoding="utf-8")
    assert "/api/download-contract?name=AcademicCalendar" in js
    assert "AcademicCalendar" in library._CONTRACT_FILE_MAP
