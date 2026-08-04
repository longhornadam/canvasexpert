"""Focused tests for the custom-routine ``combined_calendar`` seam: an
explicit ok/state/problems/repair_url on failure, never a usable partial
no-count list paired with a hidden failure.
"""
import pytest

from api.tests.calendar_fixtures import write_school_calendar
from api.webui import workspace
from api.webui.routes import routines_custom

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
        "period_id,start,end\n1,8:00 AM,8:45 AM\n", encoding="utf-8")


def test_combined_calendar_reports_ok_false_when_unconfigured():
    result = routines_custom._combined_calendar_for_routines()
    assert result["ok"] is False
    assert result["state"] == "unconfigured"
    assert result["repair_url"] == "/calendar"
    assert "no_count_dates" not in result


def test_combined_calendar_reports_ok_false_for_an_out_of_range_request(isolated_workspace):
    calendars = isolated_workspace / "Library" / "Calendars"
    _bell_schedule(calendars)
    write_school_calendar(
        calendars, {"2026-08-17": SCHEDULE_ID}, coverage_start="2026-08-17",
        coverage_end="2026-08-18")
    result = routines_custom._combined_calendar_for_routines("2026-08-17", "2026-09-01")
    assert result["ok"] is False
    assert result["state"] == "outside_coverage"
    assert "no_count_dates" not in result


def test_combined_calendar_returns_no_count_dates_on_success(isolated_workspace):
    calendars = isolated_workspace / "Library" / "Calendars"
    _bell_schedule(calendars)
    write_school_calendar(
        calendars, {"2026-08-17": SCHEDULE_ID, "2026-08-19": SCHEDULE_ID},
        coverage_start="2026-08-17", coverage_end="2026-08-19")
    result = routines_custom._combined_calendar_for_routines("2026-08-17", "2026-08-19")
    assert result["ok"] is True
    assert result["no_count_dates"] == ["2026-08-18"]
