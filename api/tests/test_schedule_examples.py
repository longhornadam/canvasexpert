"""Integrity checks for the shipped class schedule examples."""

import csv
import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from api.webui import deck_schedule, deps, workspace
from api.webui.routes.calendar import _file_key


ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_ROOT = ROOT / "api" / "default_docs" / "Examples" / "Class Schedules"
SEEDED_CALENDARS = ROOT / "api" / "default_docs" / "Calendars"
EXPECTED_DATES = [
    "2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21",
    "2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28",
    "2026-08-31", "2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04",
    "2026-09-08", "2026-09-09", "2026-09-10", "2026-09-11",
]


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


def _example_dirs():
    return sorted(path for path in EXAMPLES_ROOT.iterdir() if path.is_dir())


def _manifest(example_dir):
    return json.loads((example_dir / "manifest.json").read_text(encoding="utf-8"))


def _loaded_example(example_dir):
    manifest = _manifest(example_dir)
    teacher = json.loads(
        (example_dir / manifest["teacher_schedule"]).read_text(encoding="utf-8")
    )
    bell = {}
    for filename in manifest["bell_schedules"]:
        content = (example_dir / filename).read_text(encoding="utf-8")
        periods, problems = deck_schedule.parse_bell_schedule(content)
        assert problems == []
        bell[_file_key(filename)] = periods
    day_calendar, problems = deck_schedule.parse_day_calendar(
        (example_dir / manifest["day_calendar"]).read_text(encoding="utf-8")
    )
    assert problems == []
    return manifest, teacher, bell, day_calendar


def test_every_example_directory_has_a_manifest():
    assert {path.name for path in _example_dirs()} == {
        "seven-single-periods", "alternating-day-split", "double-block-mixed"
    }
    for example_dir in _example_dirs():
        manifest = _manifest(example_dir)
        assert manifest["slug"] == example_dir.name
        assert manifest["format"] == "canvasexpert.schedule_example/1"


def test_every_manifest_file_exists_on_disk():
    for example_dir in _example_dirs():
        manifest = _manifest(example_dir)
        files = [manifest["teacher_schedule"], *manifest["bell_schedules"], manifest["day_calendar"]]
        assert all((example_dir / filename).is_file() for filename in files)


def test_every_example_teacher_schedule_validates():
    for example_dir in _example_dirs():
        manifest = _manifest(example_dir)
        teacher = json.loads(
            (example_dir / manifest["teacher_schedule"]).read_text(encoding="utf-8")
        )
        assert deck_schedule.validate_teacher_schedule(teacher) == []


@pytest.mark.parametrize(
    "example_dir, check_date",
    [
        (example_dir, check_date)
        for example_dir in _example_dirs()
        for check_date in _manifest(example_dir)["check_dates"]
    ],
)
def test_every_example_resolves_with_zero_problems(example_dir, check_date):
    _manifest_data, teacher, bell, day_calendar = _loaded_example(example_dir)
    _blocks, problems = deck_schedule.resolve_day(check_date, day_calendar, bell, teacher)
    assert problems == []


def test_every_example_resolves_at_least_one_block():
    for example_dir in _example_dirs():
        manifest, teacher, bell, day_calendar = _loaded_example(example_dir)
        blocks, problems = deck_schedule.resolve_day(
            manifest["check_dates"][0], day_calendar, bell, teacher
        )
        assert problems == []
        assert blocks


def test_split_example_resolves_a_different_block_set_on_each_weekday_family():
    example_dir = EXAMPLES_ROOT / "alternating-day-split"
    _manifest_data, teacher, bell, day_calendar = _loaded_example(example_dir)
    monday, _ = deck_schedule.resolve_day("2026-08-17", day_calendar, bell, teacher)
    tuesday, _ = deck_schedule.resolve_day("2026-08-18", day_calendar, bell, teacher)
    friday, _ = deck_schedule.resolve_day("2026-08-21", day_calendar, bell, teacher)
    assert {block["name"] for block in monday} != {block["name"] for block in tuesday}
    assert {block["name"] for block in monday} != {block["name"] for block in friday}
    assert {block["name"] for block in tuesday} != {block["name"] for block in friday}


def test_split_example_resolves_the_same_block_names_on_monday_and_friday():
    example_dir = EXAMPLES_ROOT / "alternating-day-split"
    _manifest_data, teacher, bell, day_calendar = _loaded_example(example_dir)
    monday, _ = deck_schedule.resolve_day("2026-08-17", day_calendar, bell, teacher)
    friday, _ = deck_schedule.resolve_day("2026-08-21", day_calendar, bell, teacher)
    monday_names = {block["name"] for block in monday} - {"Planning"}
    friday_names = {block["name"] for block in friday}
    assert monday_names <= friday_names


def test_double_block_example_spans_two_periods():
    example_dir = EXAMPLES_ROOT / "double-block-mixed"
    _manifest_data, teacher, bell, day_calendar = _loaded_example(example_dir)
    blocks, problems = deck_schedule.resolve_day("2026-08-17", day_calendar, bell, teacher)
    assert problems == []
    first = next(block for block in blocks if block["name"] == "1st/2nd")
    fifth = next(block for block in blocks if block["name"] == "5th/6th")
    assert first["raw_periods"] == [1, 2]
    assert (first["start"], first["end"]) == ("08:20", "10:04")
    assert fifth["raw_periods"] == [5, 6]
    assert (fifth["start"], fifth["end"]) == ("12:31", "14:15")


def test_examples_are_not_seeded_into_a_new_workspace(isolated_workspace):
    workspace.ensure_workspace()
    calendars = isolated_workspace / "Library" / "Calendars"
    smartdecks = isolated_workspace / "Library" / "SmartDecks"
    assert not list(calendars.glob("*Example*"))
    assert not (smartdecks / "Teacher Schedule.json").exists()


def test_example_bell_schedule_filenames_are_discoverable(isolated_workspace):
    calendars = isolated_workspace / "Library" / "Calendars"
    calendars.mkdir(parents=True)
    expected = set()
    for example_dir in _example_dirs():
        manifest = _manifest(example_dir)
        for filename in manifest["bell_schedules"]:
            shutil.copy2(example_dir / filename, calendars / filename)
            expected.add(filename)
    found = {entry["name"] for entry in deps.list_bell_schedule_files()}
    assert found == expected


def test_example_day_calendar_filenames_are_not_mistaken_for_bell_schedules(isolated_workspace):
    calendars = isolated_workspace / "Library" / "Calendars"
    calendars.mkdir(parents=True)
    example_dir = EXAMPLES_ROOT / "seven-single-periods"
    manifest = _manifest(example_dir)
    for filename in [manifest["bell_schedules"][0], manifest["day_calendar"]]:
        shutil.copy2(example_dir / filename, calendars / filename)
    found = {entry["name"] for entry in deps.list_bell_schedule_files()}
    assert manifest["day_calendar"] not in found
    assert manifest["bell_schedules"][0] in found


def test_example_day_calendar_schedule_ids_match_its_bell_schedule_slugs():
    for example_dir in _example_dirs():
        manifest, _teacher, bell, day_calendar = _loaded_example(example_dir)
        assert set(day_calendar.values()) <= set(bell)
        assert set(bell) == {_file_key(filename) for filename in manifest["bell_schedules"]}


def test_example_day_calendar_dates_match_the_weekday_pattern_in_its_manifest():
    for example_dir in _example_dirs():
        manifest, _teacher, _bell, day_calendar = _loaded_example(example_dir)
        assert list(day_calendar) == EXPECTED_DATES
        assert all(date.fromisoformat(value).weekday() < 5 for value in day_calendar)
        assert "2026-09-07" not in day_calendar
        assert set(manifest["check_dates"]) <= set(day_calendar)


def test_example_bell_times_do_not_match_the_seeded_district_times():
    seeded = []
    for path in SEEDED_CALENDARS.glob("Bell Schedule - *.csv"):
        with path.open(newline="", encoding="utf-8") as handle:
            seeded.append({row["start"] for row in csv.DictReader(handle)})

    for example_dir in _example_dirs():
        manifest = _manifest(example_dir)
        for filename in manifest["bell_schedules"]:
            with (example_dir / filename).open(newline="", encoding="utf-8") as handle:
                starts = {row["start"] for row in csv.DictReader(handle)}
            assert all(starts != seeded_starts for seeded_starts in seeded)
