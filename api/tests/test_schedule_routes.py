"""Class schedule setup route tests."""

import json
import shutil
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.webui import config, workspace
from api.webui.server import app


client = TestClient(app)
FIXTURE = Path(__file__).parent / "fixtures" / "class_schedule"


@pytest.fixture(autouse=True)
def isolated_workspace(tmp_path, monkeypatch):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(workspace_root))
    monkeypatch.setattr(
        workspace, "library_folder", lambda name: str(workspace_root / "Library" / name)
    )
    monkeypatch.setattr(
        workspace, "system_folder", lambda name: str(workspace_root / "_System" / name)
    )
    monkeypatch.setattr(workspace, "path_within_workspace", lambda p: True)
    return workspace_root


def _folders(root):
    calendars = root / "Library" / "Calendars"
    smartdecks = root / "Library" / "SmartDecks"
    calendars.mkdir(parents=True, exist_ok=True)
    smartdecks.mkdir(parents=True, exist_ok=True)
    return calendars, smartdecks


def test_get_api_schedule_on_empty_workspace_reports_all_three_missing(isolated_workspace):
    response = client.get("/api/schedule")
    data = response.json()
    assert response.status_code == 200
    assert data["ok"] is True
    assert data["ready"] is False
    assert data["pieces"]["teacher_schedule"]["present"] is False
    assert data["pieces"]["bell_schedules"]["present"] is False
    assert data["pieces"]["day_calendar"]["present"] is False
    assert "no teacher schedule found" in data["missing"]
    assert "no bell schedules found" in data["missing"]
    assert "no day calendar found" in data["missing"]


def test_get_api_schedule_reports_missing_bell_schedules_explicitly(isolated_workspace):
    calendars, smartdecks = _folders(isolated_workspace)
    (smartdecks / "Teacher Schedule.json").write_text(
        json.dumps({"blocks": [{"name": "Algebra", "raw_periods": [1]}]}),
        encoding="utf-8",
    )
    (calendars / "Day Calendar.csv").write_text(
        "date,schedule_id\n2026-08-17,missing_bell\n", encoding="utf-8"
    )
    data = client.get("/api/schedule").json()
    assert data["ready"] is False
    assert "no bell schedules found" in data["missing"]
    assert data["pieces"]["bell_schedules"]["found"] == []


def test_get_api_schedule_reports_unknown_schedule_ids_in_the_day_calendar(isolated_workspace):
    calendars, smartdecks = _folders(isolated_workspace)
    (smartdecks / "Teacher Schedule.json").write_text(
        json.dumps({"blocks": [{"name": "Algebra", "raw_periods": [1]}]}),
        encoding="utf-8",
    )
    (calendars / "Bell Schedule - Example.csv").write_text(
        "period_id,start,end\n1,08:00,08:45\n", encoding="utf-8"
    )
    (calendars / "Day Calendar.csv").write_text(
        "date,schedule_id\n2026-08-17,renamed_schedule\n", encoding="utf-8"
    )
    data = client.get("/api/schedule").json()
    assert data["pieces"]["day_calendar"]["unknown_schedule_ids"] == ["renamed_schedule"]


def test_get_api_schedule_reports_a_day_calendar_that_ran_out(isolated_workspace):
    calendars, smartdecks = _folders(isolated_workspace)
    today = date.today()
    yesterday = (today - timedelta(days=1)).isoformat()
    tomorrow = (today + timedelta(days=1)).isoformat()
    (smartdecks / "Teacher Schedule.json").write_text(
        json.dumps({"blocks": [{"name": "Algebra", "raw_periods": [1]}]}),
        encoding="utf-8",
    )
    (calendars / "Bell Schedule - Example.csv").write_text(
        "period_id,start,end\n1,08:00,08:45\n", encoding="utf-8"
    )
    day_path = calendars / "Day Calendar.csv"

    def ends_before_today(*dates):
        rows = "".join(f"{value},bell_schedule_example\n" for value in dates)
        day_path.write_text(f"date,schedule_id\n{rows}", encoding="utf-8")
        return client.get("/api/schedule").json()["pieces"]["day_calendar"]["ends_before_today"]

    assert ends_before_today(yesterday) is True
    assert ends_before_today(today.isoformat()) is False
    assert ends_before_today(tomorrow) is False
    # Weekends and holidays are absent from a healthy calendar, so a gap over
    # today is not exhaustion as long as later dates remain.
    assert ends_before_today(yesterday, tomorrow) is False


def test_get_api_schedule_returns_blocks_verbatim_including_unknown_keys(isolated_workspace):
    _calendars, smartdecks = _folders(isolated_workspace)
    blocks = [{"name": "Algebra", "raw_periods": [1], "weekdays": [0], "custom": {"x": 1}}]
    (smartdecks / "Teacher Schedule.json").write_text(
        json.dumps({"_comment": "keep", "version": "1.0-json", "blocks": blocks}),
        encoding="utf-8",
    )
    assert client.get("/api/schedule").json()["blocks"] == blocks


def test_schedule_course_binding_round_trip_reports_unknown_ids_and_lists_saved_courses(
    isolated_workspace, monkeypatch
):
    courses = [
        {"id": "9000001", "name": "Course A", "nickname": "A", "active": True},
        {"id": "9000002", "name": "Course B", "nickname": "", "active": False},
    ]
    monkeypatch.setattr(config, "saved_courses", lambda: courses)
    monkeypatch.setattr(
        config, "course_display_name",
        lambda course_id: {"9000001": "A", "9000002": "Course B"}[str(course_id)],
    )
    blocks = [{
        "name": "Algebra",
        "raw_periods": [1, 2],
        "label": "Math 7",
        "course_id": "missing-course",
        "weekdays": [0, 2],
        "custom": {"keep": True},
    }]

    response = client.post("/api/schedule/teacher", data={"blocks": json.dumps(blocks)})
    assert response.json()["ok"] is True

    data = client.get("/api/schedule").json()
    assert data["blocks"] == blocks
    assert data["courses"] == [
        {"id": "9000001", "name": "A", "active": True},
        {"id": "9000002", "name": "Course B", "active": False},
    ]
    assert data["pieces"]["teacher_schedule"]["unknown_course_ids"] == ["missing-course"]


def test_post_schedule_teacher_writes_blocks(isolated_workspace):
    blocks = [{"name": "Algebra", "raw_periods": [1], "weekdays": [0]}]
    response = client.post("/api/schedule/teacher", data={"blocks": json.dumps(blocks)})
    assert response.json()["ok"] is True
    path = isolated_workspace / "Library" / "SmartDecks" / "Teacher Schedule.json"
    assert json.loads(path.read_text(encoding="utf-8"))["blocks"] == blocks


def test_post_schedule_teacher_creates_the_file_when_absent(isolated_workspace):
    response = client.post(
        "/api/schedule/teacher",
        data={"blocks": json.dumps([{"name": "Algebra", "raw_periods": [1]}])},
    )
    saved = json.loads(
        (isolated_workspace / "Library" / "SmartDecks" / "Teacher Schedule.json").read_text(
            encoding="utf-8"
        )
    )
    assert response.json()["count"] == 1
    assert saved["version"] == "1.0-json"


def test_post_schedule_teacher_preserves_unknown_top_level_keys(isolated_workspace):
    _calendars, smartdecks = _folders(isolated_workspace)
    original = {"_comment": "keep this", "custom": {"source": "hand"}, "blocks": []}
    path = smartdecks / "Teacher Schedule.json"
    path.write_text(json.dumps(original), encoding="utf-8")
    client.post(
        "/api/schedule/teacher",
        data={"blocks": json.dumps([{"name": "Algebra", "raw_periods": [1]}])},
    )
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["_comment"] == original["_comment"]
    assert saved["custom"] == original["custom"]


def test_post_schedule_teacher_sets_version_only_when_absent(isolated_workspace):
    _calendars, smartdecks = _folders(isolated_workspace)
    path = smartdecks / "Teacher Schedule.json"
    path.write_text(json.dumps({"version": "custom", "blocks": []}), encoding="utf-8")
    client.post(
        "/api/schedule/teacher",
        data={"blocks": json.dumps([{"name": "Algebra", "raw_periods": [1]}])},
    )
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == "custom"


def test_post_schedule_teacher_keeps_block_order(isolated_workspace):
    blocks = [
        {"name": "Later", "raw_periods": [2]},
        {"name": "Earlier", "raw_periods": [1]},
    ]
    client.post("/api/schedule/teacher", data={"blocks": json.dumps(blocks)})
    saved = json.loads(
        (isolated_workspace / "Library" / "SmartDecks" / "Teacher Schedule.json").read_text(
            encoding="utf-8"
        )
    )
    assert [block["name"] for block in saved["blocks"]] == ["Later", "Earlier"]


def test_saving_the_fixture_schedule_back_unchanged_keeps_every_block(isolated_workspace):
    """A no-op editor round trip must leave every block exactly as it was.

    A block's name is the key a slide binds to, and two blocks may legitimately
    share a course label. An editor that derives one from the other renames blocks
    on save and trips the duplicate-name check, so a realistic multi-block schedule
    has to survive being read and written straight back.
    """
    _calendars, smartdecks = _folders(isolated_workspace)
    shutil.copy2(FIXTURE / "Teacher Schedule.json", smartdecks / "Teacher Schedule.json")

    blocks = client.get("/api/schedule").json()["blocks"]
    assert len(blocks) > 1
    assert len({block["name"] for block in blocks}) < len(blocks), (
        "fixture should contain a shared block name, which is the case that used to break"
    )

    response = client.post("/api/schedule/teacher", data={"blocks": json.dumps(blocks)})
    assert response.json()["ok"] is True, response.json().get("problems")
    assert client.get("/api/schedule").json()["blocks"] == blocks


def test_post_schedule_teacher_refuses_invalid_blocks_and_leaves_the_file_unchanged(isolated_workspace):
    _calendars, smartdecks = _folders(isolated_workspace)
    path = smartdecks / "Teacher Schedule.json"
    original = '{"_comment":"keep","blocks":[{"name":"Old","raw_periods":[1]}]}'
    path.write_text(original, encoding="utf-8")
    response = client.post(
        "/api/schedule/teacher",
        data={"blocks": json.dumps([{"name": "", "raw_periods": []}])},
    )
    assert response.json()["ok"] is False
    assert path.read_text(encoding="utf-8") == original
