"""Focused tests for gradebook_service's extra-time due/lock split: fails
closed on a broken Calendar instead of silently dropping extended overrides.
"""
import pytest

from api.tests.calendar_fixtures import write_school_calendar
from api.platform_services import workspace
from api.webui import gradebook_service

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


def test_split_returns_standard_only_when_no_roster_or_due_date(monkeypatch):
    monkeypatch.setattr(gradebook_service.config, "get_extra_time", lambda course_id: [])
    result = gradebook_service._split_for_extra_time("1", ["10", "20"], None)
    assert result == {"ok": True, "standard": ["10", "20"], "extended": []}


def test_split_fails_closed_when_calendar_is_unconfigured(monkeypatch):
    monkeypatch.setattr(gradebook_service.config, "get_extra_time",
                        lambda course_id: [{"id": "10", "days": 2}])
    result = gradebook_service._split_for_extra_time(
        "1", ["10", "20"], "2026-08-19T23:59:00-05:00")
    assert result["ok"] is False
    assert "attention" in result["error"].lower()


def test_split_computes_extended_due_dates_on_a_ready_calendar(isolated_workspace, monkeypatch):
    calendars = isolated_workspace / "Library" / "Calendars"
    _bell_schedule(calendars)
    write_school_calendar(
        calendars, {"2026-08-19": SCHEDULE_ID, "2026-08-21": SCHEDULE_ID, "2026-08-24": SCHEDULE_ID},
        coverage_start="2026-08-17", coverage_end="2026-08-28")
    monkeypatch.setattr(gradebook_service.config, "get_extra_time",
                        lambda course_id: [{"id": "10", "days": 2}])

    result = gradebook_service._split_for_extra_time(
        "1", ["10", "20"], "2026-08-19T23:59:00-05:00")
    assert result["ok"] is True
    assert result["standard"] == ["20"]
    assert len(result["extended"]) == 1
    assert result["extended"][0]["due_at"].startswith("2026-08-24")


def test_expand_variants_extra_time_attaches_error_instead_of_dropping_the_override(monkeypatch):
    monkeypatch.setattr(gradebook_service.config, "get_extra_time",
                        lambda course_id: [{"id": "10", "days": 2}])
    entries = [{"label": "Tier A", "student_ids": ["10", "20"]}]
    result = gradebook_service._expand_variants_extra_time(
        "1", entries, '{"due_at": "2026-08-19T23:59:00-05:00"}')
    assert "extra_time_error" in result[0]
    assert "overrides" not in result[0]
