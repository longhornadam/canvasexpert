import json

from fastapi.testclient import TestClient

from api.platform_services import workspace
from api.webui import bell_schedule, school_calendar
from api.webui.server import app


_CONTENT = """label,end,period_id,start
Lunch,12:15 PM, lunch,11:45 AM
Core,11:40 AM, core,8:00 AM
"""
_CANONICAL = """period_id,start,end,label
core,8:00 AM,11:40 AM,Core
lunch,11:45 AM,12:15 PM,Lunch
"""


def _seed_schedule(tmp_path, name="Bell Schedule - Ordinary.csv", content=_CANONICAL):
    calendars = tmp_path / "Library" / "Calendars"
    calendars.mkdir(parents=True, exist_ok=True)
    (calendars / name).write_text(content, encoding="utf-8")
    return calendars


def test_preview_normalizes_without_writing_and_apply_is_digest_safe(tmp_path):
    _seed_schedule(tmp_path)

    preview, problems = bell_schedule.preview_bell_schedule(
        schedule_id="Bell_Schedule_Ordinary", content=_CONTENT, root=str(tmp_path))

    assert problems == []
    assert preview["before"]["meetings"][0]["period_id"] == "core"
    assert preview["after"]["meetings"][1]["period_id"] == "lunch"
    # The source file is read as raw bytes, so the preview also normalizes its
    # Windows line endings into the canonical LF representation.
    assert preview["is_noop"] is False
    assert preview["preview_digest"]
    assert (tmp_path / "Library" / "Calendars" / "Bell Schedule - Ordinary.csv").read_text(encoding="utf-8") == _CANONICAL

    result, problems = bell_schedule.apply_bell_schedule(
        preview, expected_digest=preview["base_digest"], root=str(tmp_path))
    assert problems == []
    assert result["changed"] is True
    assert (tmp_path / "Library" / "Calendars" / "Bell Schedule - Ordinary.csv").read_text(encoding="utf-8") == _CANONICAL


def test_apply_writes_new_schedule_and_refuses_stale_or_altered_preview(tmp_path):
    _seed_schedule(tmp_path)
    preview, problems = bell_schedule.preview_bell_schedule(
        schedule_id="bell_schedule_late_start", content=_CANONICAL, root=str(tmp_path))
    assert problems == []
    target = tmp_path / "Library" / "Calendars" / "Bell Schedule - Late Start.csv"
    assert not target.exists()

    altered = {**preview, "after": {**preview["after"], "meetings": []}}
    result, problems = bell_schedule.apply_bell_schedule(
        altered, expected_digest=preview["base_digest"], root=str(tmp_path))
    assert result is None
    assert any("after projection" in problem for problem in problems)
    assert not target.exists()

    result, problems = bell_schedule.apply_bell_schedule(
        preview, expected_digest="stale", root=str(tmp_path))
    assert result is None
    assert any("base digest" in problem for problem in problems)

    result, problems = bell_schedule.apply_bell_schedule(
        preview, expected_digest=preview["base_digest"], root=str(tmp_path))
    assert problems == []
    assert result["changed"] is True
    assert target.read_text(encoding="utf-8") == _CANONICAL


def test_preview_refuses_orphaned_calendar_reference(tmp_path):
    _seed_schedule(tmp_path)
    school_calendar.create_school_year(
        school_year="2026-27", coverage_start="2026-08-17", coverage_end="2026-08-17",
        default_schedule_id="bell_schedule_missing", root=str(tmp_path))

    preview, problems = bell_schedule.preview_bell_schedule(
        schedule_id="bell_schedule_ordinary", content=_CANONICAL, root=str(tmp_path))

    assert preview is None
    assert any("no file" in problem for problem in problems)


