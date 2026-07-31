"""Class schedule setup route tests."""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.webui import workspace
from api.webui.server import app


client = TestClient(app)
ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "api" / "default_docs" / "Examples" / "Class Schedules"


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


def _example_files(slug):
    example = EXAMPLES / slug
    manifest = json.loads((example / "manifest.json").read_text(encoding="utf-8"))
    files = [manifest["teacher_schedule"], *manifest["bell_schedules"], manifest["day_calendar"]]
    return example, manifest, files


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


def test_get_api_schedule_returns_blocks_verbatim_including_unknown_keys(isolated_workspace):
    _calendars, smartdecks = _folders(isolated_workspace)
    blocks = [{"name": "Algebra", "raw_periods": [1], "weekdays": [0], "custom": {"x": 1}}]
    (smartdecks / "Teacher Schedule.json").write_text(
        json.dumps({"_comment": "keep", "version": "1.0-json", "blocks": blocks}),
        encoding="utf-8",
    )
    assert client.get("/api/schedule").json()["blocks"] == blocks


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


def test_load_example_writes_every_manifest_file(isolated_workspace):
    _example, manifest, files = _example_files("alternating-day-split")
    response = client.post("/api/schedule/examples/load", data={"slug": "alternating-day-split"})
    data = response.json()
    assert data["ok"] is True
    assert set(data["written"]) == set(files)
    for filename in files:
        folder = "SmartDecks" if filename == "Teacher Schedule.json" else "Calendars"
        assert (isolated_workspace / "Library" / folder / filename).exists()


def test_load_example_does_not_write_the_manifest_or_readme(isolated_workspace):
    client.post("/api/schedule/examples/load", data={"slug": "seven-single-periods"})
    assert not list((isolated_workspace / "Library").rglob("manifest.json"))
    assert not list((isolated_workspace / "Library").rglob("README.md"))


def test_load_example_refuses_to_clobber_an_existing_teacher_schedule(isolated_workspace):
    _calendars, smartdecks = _folders(isolated_workspace)
    teacher = smartdecks / "Teacher Schedule.json"
    teacher.write_text('{"blocks":[]}', encoding="utf-8")
    data = client.post(
        "/api/schedule/examples/load", data={"slug": "seven-single-periods"}
    ).json()
    assert data["ok"] is False
    assert data["conflict"] == "teacher_schedule"
    assert teacher.read_text(encoding="utf-8") == '{"blocks":[]}'
    assert not list((isolated_workspace / "Library" / "Calendars").glob("*.csv"))


def test_load_example_with_overwrite_moves_the_old_file_aside(isolated_workspace):
    _calendars, smartdecks = _folders(isolated_workspace)
    teacher = smartdecks / "Teacher Schedule.json"
    teacher.write_text('{"blocks":[{"name":"Old","raw_periods":[1]}]}', encoding="utf-8")
    data = client.post(
        "/api/schedule/examples/load",
        data={"slug": "seven-single-periods", "overwrite": "true"},
    ).json()
    assert data["ok"] is True
    moved = list(smartdecks.glob("Teacher Schedule (replaced *.json"))
    assert len(moved) == 1
    assert json.loads(moved[0].read_text(encoding="utf-8"))["blocks"][0]["name"] == "Old"


def test_load_example_skips_csvs_that_already_exist(isolated_workspace):
    calendars, _smartdecks = _folders(isolated_workspace)
    source = EXAMPLES / "seven-single-periods" / "Bell Schedule - Example Seven Period Day.csv"
    existing = calendars / source.name
    existing.write_text("existing", encoding="utf-8")
    data = client.post(
        "/api/schedule/examples/load", data={"slug": "seven-single-periods"}
    ).json()
    assert data["ok"] is True
    assert source.name in data["skipped"]
    assert existing.read_text(encoding="utf-8") == "existing"


def test_load_example_reports_day_calendar_overlap(isolated_workspace):
    calendars, _smartdecks = _folders(isolated_workspace)
    (calendars / "Existing Day Calendar.csv").write_text(
        "date,schedule_id\n2026-08-17,existing\n2026-10-01,existing\n", encoding="utf-8"
    )
    data = client.post(
        "/api/schedule/examples/load", data={"slug": "seven-single-periods"}
    ).json()
    assert data["day_calendar_overlap"] == 1


def test_load_example_rejects_an_unknown_slug():
    data = client.post("/api/schedule/examples/load", data={"slug": "no-such-example"}).json()
    assert data["ok"] is False
    assert data["problems"]


def test_loaded_example_makes_readiness_ready(isolated_workspace):
    client.post("/api/schedule/examples/load", data={"slug": "alternating-day-split"})
    data = client.get("/smartdeck/api/readiness").json()
    assert data["ready"] is True
    assert data["missing"] == []


def test_remove_example_moves_unmodified_files_to_the_system_archive(isolated_workspace):
    _example, _manifest, files = _example_files("seven-single-periods")
    client.post("/api/schedule/examples/load", data={"slug": "seven-single-periods"})
    data = client.post(
        "/api/schedule/examples/remove", data={"slug": "seven-single-periods"}
    ).json()
    archive = isolated_workspace / "_System" / "Archive" / "Class Schedule Examples" / "seven-single-periods"
    assert data["ok"] is True
    assert set(data["moved"]) == set(files)
    assert all((archive / filename).exists() for filename in files)


def test_remove_example_keeps_a_file_the_teacher_edited(isolated_workspace):
    _example, _manifest, _files = _example_files("seven-single-periods")
    client.post("/api/schedule/examples/load", data={"slug": "seven-single-periods"})
    teacher = isolated_workspace / "Library" / "SmartDecks" / "Teacher Schedule.json"
    edited = json.loads(teacher.read_text(encoding="utf-8"))
    edited["blocks"][0]["name"] = "Edited block"
    teacher.write_text(json.dumps(edited, indent=2), encoding="utf-8")
    data = client.post(
        "/api/schedule/examples/remove", data={"slug": "seven-single-periods"}
    ).json()
    assert data["ok"] is True
    assert "Teacher Schedule.json" in data["kept"]
    assert teacher.exists()
