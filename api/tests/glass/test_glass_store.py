"""Day plan reads out of the workspace.

Every test runs against tmp_path with a monkeypatched workspace root, so no
real synced workspace is read or written. A missing plan is the common case on
a busy morning, so it is checked first.
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from api.glass import schema, store
from api.schedule import loader
from api.webui import workspace

ON = date(2099, 9, 14)


def _plan_data(**overrides):
    data = {
        "format": schema.DAY_PLAN_FORMAT,
        "date": ON.isoformat(),
        "sections": {
            "p1": {
                "learning_goal": "Explain how point of view shapes what a reader knows",
                "work": [{"name": "Point of view sort", "detail": "Finish page 2"}],
            },
        },
    }
    data.update(overrides)
    return data


@pytest.fixture
def plans_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    folder = tmp_path / "Library" / "Glass" / "day-plans"
    folder.mkdir(parents=True)
    return folder


def _write(folder, name: str, payload) -> None:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    (folder / name).write_text(text, encoding="utf-8")


def test_the_plan_path_is_the_date(plans_folder):
    assert store.day_plan_path(ON) == str(plans_folder / "2099-09-14.json")


def test_a_missing_plan_is_a_note_not_a_crash(plans_folder):
    plan, notes = store.load_day_plan(ON)

    assert plan is None
    assert len(notes) == 1
    assert "2099-09-14" in notes[0]


def test_a_missing_folder_is_a_note_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))

    plan, notes = store.load_day_plan(ON)

    assert plan is None
    assert notes and "2099-09-14" in notes[0]


def test_no_workspace_is_a_note_not_a_crash(monkeypatch):
    monkeypatch.setattr(workspace, "workspace_root", lambda: None)

    assert store.day_plans_folder() is None
    plan, notes = store.load_day_plan(ON)

    assert plan is None
    assert notes and "workspace" in notes[0]


def test_a_written_plan_loads_cleanly(plans_folder):
    _write(plans_folder, "2099-09-14.json", _plan_data())

    plan, notes = store.load_day_plan(ON)

    assert notes == []
    assert plan.date == ON
    assert plan.section("p1").work[0].name == "Point of view sort"


def test_broken_json_is_a_note_not_a_crash(plans_folder):
    _write(plans_folder, "2099-09-14.json", "{not json")

    plan, notes = store.load_day_plan(ON)

    assert plan is None
    assert any("2099-09-14.json" in note for note in notes)


def test_a_plan_that_cannot_be_understood_is_a_note_not_a_crash(plans_folder):
    _write(plans_folder, "2099-09-14.json", {"format": "something.else/1"})

    plan, notes = store.load_day_plan(ON)

    assert plan is None
    assert any(schema.DAY_PLAN_FORMAT in note for note in notes)


def test_a_date_that_disagrees_with_the_file_name_is_flagged(plans_folder):
    _write(plans_folder, "2099-09-14.json", _plan_data(date="2099-09-15"))

    plan, notes = store.load_day_plan(ON)

    # The plan is still shown: a wrong date field is worth mentioning, not
    # worth blanking the screen over.
    assert plan is not None
    assert any("2099-09-15" in note for note in notes)


def test_available_plan_dates_are_sorted_and_date_named_only(plans_folder):
    for name in ("2099-09-14.json", "2099-09-08.json", "2099-10-16.json"):
        _write(plans_folder, name, _plan_data())
    _write(plans_folder, "notes-to-self.json", _plan_data())
    _write(plans_folder, "2099-09-09.txt", "not a plan")

    assert store.available_plan_dates() == [
        date(2099, 9, 8), date(2099, 9, 14), date(2099, 10, 16),
    ]


def test_available_plan_dates_is_empty_without_a_workspace(monkeypatch):
    monkeypatch.setattr(workspace, "workspace_root", lambda: None)

    assert store.available_plan_dates() == []


def test_glass_folder_is_the_one_library_folder(plans_folder):
    folder = store.glass_folder()

    assert folder.endswith("Glass")
    assert workspace.LIBRARY_NAME in folder
    assert workspace.SYSTEM_NAME not in folder
    # The bell schedule and the day plans share it.
    assert loader.bell_schedule_folder() == folder
