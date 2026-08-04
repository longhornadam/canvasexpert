"""Class schedule setup route tests."""

import json
import shutil
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
    calendars.mkdir(parents=True, exist_ok=True)
    return calendars


def _bell_schedule(calendars):
    path = calendars / "Bell Schedule - Example.csv"
    path.write_text(
        "period_id,start,end\n"
        "1,8:00 AM,8:45 AM\n"
        "2,8:50 AM,9:35 AM\n"
        "3,9:40 AM,10:25 AM\n"
        "4,10:30 AM,11:15 AM\n"
        "5,11:20 AM,12:05 PM\n"
        "6,12:10 PM,12:55 PM\n"
        "7,1:00 PM,1:45 PM\n"
        "8,1:50 PM,2:35 PM\n",
        encoding="utf-8",
    )


def test_get_api_schedule_on_empty_workspace_reports_both_missing(isolated_workspace):
    response = client.get("/api/schedule")
    data = response.json()
    assert response.status_code == 200
    assert data["ok"] is True
    assert data["ready"] is False
    assert data["pieces"]["teacher_schedule"]["present"] is False
    assert data["pieces"]["bell_schedules"]["present"] is False
    assert "no teacher schedule found" in data["missing"]
    assert "no bell schedules found" in data["missing"]


def test_get_api_schedule_reports_missing_bell_schedules_explicitly(isolated_workspace):
    calendars = _folders(isolated_workspace)
    (calendars / "Teacher Schedule.json").write_text(
        json.dumps({"blocks": [{"name": "Algebra", "raw_periods": [1]}]}),
        encoding="utf-8",
    )
    data = client.get("/api/schedule").json()
    assert data["ready"] is False
    assert "no bell schedules found" in data["missing"]
    assert data["pieces"]["bell_schedules"]["found"] == []


def test_get_api_schedule_returns_blocks_verbatim_including_unknown_keys(isolated_workspace):
    calendars = _folders(isolated_workspace)
    blocks = [{"name": "Algebra", "raw_periods": [1], "weekdays": [0], "custom": {"x": 1}}]
    (calendars / "Teacher Schedule.json").write_text(
        json.dumps({"_comment": "keep", "version": "1.0-json", "blocks": blocks}),
        encoding="utf-8",
    )
    assert client.get("/api/schedule").json()["blocks"] == blocks


def test_schedule_course_binding_lists_saved_courses(isolated_workspace, monkeypatch):
    calendars = _folders(isolated_workspace)
    _bell_schedule(calendars)
    courses = [
        {"id": "9000001", "name": "Course A", "nickname": "A", "active": True},
        {"id": "9000002", "name": "Course B", "nickname": "", "active": False},
    ]
    monkeypatch.setattr(config, "saved_courses", lambda: courses)
    monkeypatch.setattr(config, "active_courses", lambda: [c for c in courses if c["active"]])
    monkeypatch.setattr(
        config, "course_display_name",
        lambda course_id: {"9000001": "A", "9000002": "Course B"}[str(course_id)],
    )
    blocks = [{
        "name": "Algebra",
        "raw_periods": [1, 2],
        "label": "Math 7",
        "course_id": "9000001",
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


def test_schedule_course_binding_rejects_a_non_current_course_id(isolated_workspace, monkeypatch):
    calendars = _folders(isolated_workspace)
    _bell_schedule(calendars)
    courses = [{"id": "9000001", "name": "Course A", "nickname": "A", "active": True}]
    monkeypatch.setattr(config, "saved_courses", lambda: courses)
    monkeypatch.setattr(config, "active_courses", lambda: courses)
    blocks = [{"name": "Algebra", "raw_periods": [1], "course_id": "missing-course"}]

    response = client.post("/api/schedule/teacher", data={"blocks": json.dumps(blocks)})
    data = response.json()
    assert data["ok"] is False
    assert "not a Current course" in data["problems"][0]


def test_schedule_reports_unknown_course_id_already_on_disk_without_blocking_the_read(
    isolated_workspace, monkeypatch
):
    calendars = _folders(isolated_workspace)
    courses = [{"id": "9000001", "name": "Course A", "nickname": "A", "active": True}]
    monkeypatch.setattr(config, "saved_courses", lambda: courses)
    monkeypatch.setattr(config, "active_courses", lambda: courses)
    (calendars / "Teacher Schedule.json").write_text(
        json.dumps({"blocks": [{"name": "Algebra", "raw_periods": [1],
                                "course_id": "missing-course"}]}),
        encoding="utf-8",
    )
    data = client.get("/api/schedule").json()
    assert data["pieces"]["teacher_schedule"]["unknown_course_ids"] == ["missing-course"]


def test_post_schedule_teacher_writes_blocks(isolated_workspace):
    calendars = _folders(isolated_workspace)
    _bell_schedule(calendars)
    blocks = [{"name": "Algebra", "raw_periods": [1]}]
    response = client.post("/api/schedule/teacher", data={"blocks": json.dumps(blocks)})
    assert response.json()["ok"] is True
    path = isolated_workspace / "Library" / "Calendars" / "Teacher Schedule.json"
    assert json.loads(path.read_text(encoding="utf-8"))["blocks"] == blocks


def test_post_schedule_teacher_creates_the_file_when_absent(isolated_workspace):
    calendars = _folders(isolated_workspace)
    _bell_schedule(calendars)
    response = client.post(
        "/api/schedule/teacher",
        data={"blocks": json.dumps([{"name": "Algebra", "raw_periods": [1]}])},
    )
    saved = json.loads(
        (isolated_workspace / "Library" / "Calendars" / "Teacher Schedule.json").read_text(
            encoding="utf-8"
        )
    )
    assert response.json()["count"] == 1
    assert saved["version"] == "1.0-json"


def test_post_schedule_teacher_preserves_unknown_top_level_keys(isolated_workspace):
    calendars = _folders(isolated_workspace)
    original = {"_comment": "keep this", "custom": {"source": "hand"}, "blocks": []}
    path = calendars / "Teacher Schedule.json"
    path.write_text(json.dumps(original), encoding="utf-8")
    client.post(
        "/api/schedule/teacher",
        data={"blocks": json.dumps([{"name": "Algebra", "raw_periods": [1]}])},
    )
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["_comment"] == original["_comment"]
    assert saved["custom"] == original["custom"]


def test_post_schedule_teacher_sets_version_only_when_absent(isolated_workspace):
    calendars = _folders(isolated_workspace)
    path = calendars / "Teacher Schedule.json"
    path.write_text(json.dumps({"version": "custom", "blocks": []}), encoding="utf-8")
    client.post(
        "/api/schedule/teacher",
        data={"blocks": json.dumps([{"name": "Algebra", "raw_periods": [1]}])},
    )
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == "custom"


def test_post_schedule_teacher_keeps_block_order(isolated_workspace):
    calendars = _folders(isolated_workspace)
    _bell_schedule(calendars)
    blocks = [
        {"name": "Later", "raw_periods": [2]},
        {"name": "Earlier", "raw_periods": [1]},
    ]
    client.post("/api/schedule/teacher", data={"blocks": json.dumps(blocks)})
    saved = json.loads(
        (isolated_workspace / "Library" / "Calendars" / "Teacher Schedule.json").read_text(
            encoding="utf-8"
        )
    )
    assert [block["name"] for block in saved["blocks"]] == ["Later", "Earlier"]


def test_saving_the_fixture_schedule_back_unchanged_keeps_every_block(isolated_workspace):
    """A no-op editor round trip must leave every block exactly as it was.

    A block's name is the key a slide binds to, and the new model has one unique
    block per course period. The full fixture must survive being read and written
    straight back.
    """
    calendars = _folders(isolated_workspace)
    _bell_schedule(calendars)
    shutil.copy2(FIXTURE / "Teacher Schedule.json", calendars / "Teacher Schedule.json")

    blocks = client.get("/api/schedule").json()["blocks"]
    assert len(blocks) > 1
    assert len({block["name"] for block in blocks}) == len(blocks)

    response = client.post("/api/schedule/teacher", data={"blocks": json.dumps(blocks)})
    assert response.json()["ok"] is True, response.json().get("problems")
    assert client.get("/api/schedule").json()["blocks"] == blocks


def test_post_schedule_teacher_refuses_invalid_blocks_and_leaves_the_file_unchanged(isolated_workspace):
    calendars = _folders(isolated_workspace)
    path = calendars / "Teacher Schedule.json"
    original = '{"_comment":"keep","blocks":[{"name":"Old","raw_periods":[1]}]}'
    path.write_text(original, encoding="utf-8")
    response = client.post(
        "/api/schedule/teacher",
        data={"blocks": json.dumps([{"name": "", "raw_periods": []}])},
    )
    assert response.json()["ok"] is False
    assert path.read_text(encoding="utf-8") == original
