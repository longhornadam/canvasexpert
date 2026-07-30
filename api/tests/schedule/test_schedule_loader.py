"""Bell schedule loading: the shipped files, and the sample-versus-real rule.

Everything here works against tmp_path plus a monkeypatched workspace root, so
no test reads or writes a real synced workspace.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, time

import pytest

from api.schedule import loader
from api.schedule.models import SCHEDULE_FORMAT
from api.webui import workspace


def _schedule_data(**overrides):
    """A minimal well-formed schedule, with invented times."""
    data = {
        "format": SCHEDULE_FORMAT,
        "school": "Mockingbird Junior High",
        "timezone": "America/Chicago",
        "day_types": {
            "friday": {
                "label": "Friday",
                "blocks": [
                    {"id": "p1", "kind": "class", "label": "1st Period",
                     "start": "08:30", "end": "09:24"},
                    {"id": "p4", "kind": "class", "label": "4th Period",
                     "start": "11:30", "end": "13:00",
                     "sub_blocks": {"mode": "sequential", "blocks": [
                         {"id": "p4a", "kind": "lunch", "label": "4th Period / A Lunch",
                          "start": "11:30", "end": "12:15"},
                         {"id": "p4b", "kind": "lunch", "label": "4th Period / B Lunch",
                          "start": "12:15", "end": "13:00"},
                     ]}},
                ],
            },
        },
        "weekday_default": {"4": "friday"},
        "date_overrides": {},
    }
    data.update(overrides)
    return data


@pytest.fixture
def bell_folder(tmp_path, monkeypatch):
    """An empty Library/Glass folder in a throwaway workspace."""
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    folder = tmp_path / "Library" / "Glass"
    folder.mkdir(parents=True)
    return folder


def _write(folder, name: str, data) -> str:
    path = folder / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


# ------------------------------------------------------------- shipped files
# Note: the shipped sample files from api/default_docs/Glass/ were removed
# as part of Glass feature deletion. Tests that depend on those files are skipped.


@pytest.mark.skip(reason="shipped sample files were removed with Glass feature")
def test_shipped_sample_parses():
    raise NotImplementedError("shipped sample files no longer available")

    assert schedule.school == "Mockingbird Junior High"
    assert schedule.is_sample is True
    assert set(schedule.day_types) == {
        "bobcat_hour", "friday", "homeroom_first", "pep_rally"
    }
    assert schedule.weekday_default == {
        0: "bobcat_hour", 1: "bobcat_hour", 2: "bobcat_hour",
        3: "bobcat_hour", 4: "friday",
    }
    assert schedule.date_overrides == {
        date(2099, 9, 8): "homeroom_first",
        date(2099, 10, 16): "pep_rally",
    }


@pytest.mark.skip(reason="shipped sample files were removed with Glass feature")
def test_shipped_sample_has_bobcat_hour_on_one_day_type_only():
    raise NotImplementedError("shipped sample files no longer available")

    carries = {
        day_type_id
        for day_type_id, day_type in schedule.day_types.items()
        if day_type.has_kind("bobcat_hour")
    }
    assert carries == {"bobcat_hour"}

    bobcat = schedule.day_types["bobcat_hour"].first_of_kind("bobcat_hour")
    # Bobcat Hour is the lunch hour: no A/B split, and its offerings are day
    # plan content rather than schedule content.
    assert bobcat.sub_blocks.mode == "concurrent"
    assert bobcat.sub_blocks.blocks == ()


@pytest.mark.skip(reason="shipped sample files were removed with Glass feature")
def test_shipped_sample_splits_lunch_on_the_other_three_day_types():
    raise NotImplementedError("shipped sample files no longer available")

    for day_type_id in ("friday", "homeroom_first", "pep_rally"):
        day_type = schedule.day_types[day_type_id]
        parents = [b for b in day_type.blocks if b.sub_blocks is not None]
        assert len(parents) == 1, day_type_id
        parent = parents[0]
        assert parent.sub_blocks.mode == "sequential"
        children = parent.sub_blocks.blocks
        assert len(children) == 2
        assert children[0].start == parent.start
        assert children[1].end == parent.end
        assert children[0].end == children[1].start


@pytest.mark.skip(reason="shipped sample files were removed with Glass feature")
def test_shipped_sample_reports_no_structural_problems():
    raise NotImplementedError("shipped sample files no longer available")

    assert loader._structural_problems(schedule) == []


@pytest.mark.skip(reason="shipped sample files were removed with Glass feature")
def test_shipped_template_declares_no_school_days():
    raise NotImplementedError("shipped sample files no longer available")

    # Loading the blank template by accident has to produce nothing rather than
    # wrong times, so it declares no day types and no school weekdays.
    assert schedule.is_sample is True
    assert schedule.day_types == {}
    assert schedule.weekday_default == {}
    assert schedule.day_type_id_for(date(2099, 9, 14)) is None


@pytest.mark.skip(reason="shipped sample files were removed with Glass feature")
def test_shipped_section_map_template_parses():
    raise NotImplementedError("shipped sample files no longer available")

    assert section_map.is_sample is True
    assert set(section_map.sections) == {"p4"}
    assert section_map.sections["p4"].course_id == ""


# ------------------------------------------------------------- pure parsing


def test_times_parse_from_24_hour_text():
    schedule = loader.parse_bell_schedule(_schedule_data())

    block = schedule.day_types["friday"].find("p4")
    assert block.start == time(11, 30)
    assert block.end == time(13, 0)
    assert block.duration_minutes == 90


def test_weekday_and_override_keys_become_ints_and_dates():
    schedule = loader.parse_bell_schedule(_schedule_data(
        weekday_default={"0": "friday", "4": "friday"},
        date_overrides={"2099-09-08": "friday"},
    ))

    assert schedule.weekday_default == {0: "friday", 4: "friday"}
    assert schedule.date_overrides == {date(2099, 9, 8): "friday"}
    assert schedule.day_type_id_for(date(2099, 9, 8)) == "friday"


def test_unknown_format_is_rejected_by_name():
    with pytest.raises(loader.BellScheduleError) as err:
        loader.parse_bell_schedule(_schedule_data(format="canvasexpert.bell_schedule/2"))

    assert SCHEDULE_FORMAT in str(err.value)
    assert "canvasexpert.bell_schedule/2" in str(err.value)


def test_missing_format_is_rejected_by_name():
    data = _schedule_data()
    del data["format"]

    with pytest.raises(loader.BellScheduleError) as err:
        loader.parse_bell_schedule(data)

    assert SCHEDULE_FORMAT in str(err.value)


def test_missing_start_time_names_the_day_type_and_block():
    data = _schedule_data()
    del data["day_types"]["friday"]["blocks"][1]["start"]

    with pytest.raises(loader.BellScheduleError) as err:
        loader.parse_bell_schedule(data)

    assert str(err.value) == "day type 'friday' block 'p4' has no start time"


def test_unparseable_time_names_the_block_and_the_form_wanted():
    data = _schedule_data()
    data["day_types"]["friday"]["blocks"][1]["end"] = "1:00pm"

    with pytest.raises(loader.BellScheduleError) as err:
        loader.parse_bell_schedule(data)

    message = str(err.value)
    assert "block 'p4'" in message
    assert "1:00pm" in message
    assert "13:05" in message


def test_block_without_an_id_names_the_day_type():
    data = _schedule_data()
    del data["day_types"]["friday"]["blocks"][0]["id"]

    with pytest.raises(loader.BellScheduleError) as err:
        loader.parse_bell_schedule(data)

    assert "day type 'friday' has a block with no id" in str(err.value)


def test_unknown_sub_block_mode_names_both_choices():
    data = _schedule_data()
    data["day_types"]["friday"]["blocks"][1]["sub_blocks"]["mode"] = "parallel"

    with pytest.raises(loader.BellScheduleError) as err:
        loader.parse_bell_schedule(data)

    message = str(err.value)
    assert "parallel" in message
    assert "sequential" in message
    assert "concurrent" in message


def test_weekday_default_key_that_is_not_a_number_is_explained():
    with pytest.raises(loader.BellScheduleError) as err:
        loader.parse_bell_schedule(_schedule_data(weekday_default={"Friday": "friday"}))

    message = str(err.value)
    assert "Friday" in message
    assert "Monday" in message


def test_weekday_default_key_out_of_range_is_explained():
    with pytest.raises(loader.BellScheduleError) as err:
        loader.parse_bell_schedule(_schedule_data(weekday_default={"9": "friday"}))

    assert "0" in str(err.value) and "6" in str(err.value)


def test_date_override_key_must_be_iso():
    with pytest.raises(loader.BellScheduleError) as err:
        loader.parse_bell_schedule(_schedule_data(date_overrides={"9/8/2099": "friday"}))

    assert "9/8/2099" in str(err.value)
    assert "YYYY-MM-DD" in str(err.value)


def test_optional_fields_default_sanely():
    schedule = loader.parse_bell_schedule({
        "format": SCHEDULE_FORMAT,
        "day_types": {"friday": {"blocks": [
            {"id": "p1", "start": "08:30", "end": "09:24"},
        ]}},
    })

    day_type = schedule.day_types["friday"]
    assert day_type.label == "friday"
    assert schedule.school == ""
    assert schedule.weekday_default == {}
    assert schedule.date_overrides == {}
    assert schedule.is_sample is False
    block = day_type.find("p1")
    assert block.kind == "class"
    assert block.label == "p1"
    assert block.location == ""
    assert block.sub_blocks is None


def test_inline_comment_keys_are_documentation_not_data():
    data = _schedule_data()
    data["_comment"] = "explains the file"
    data["day_types"]["_comment"] = "explains day types"
    data["weekday_default"]["_comment"] = "explains weekdays"

    schedule = loader.parse_bell_schedule(data)

    assert set(schedule.day_types) == {"friday"}
    assert schedule.weekday_default == {4: "friday"}


# --------------------------------------------------- discovery, the D5 rule


def test_one_real_file_is_used_without_a_sample_note(bell_folder):
    _write(bell_folder, "our-bells.json", _schedule_data())

    schedule, notes = loader.discover_bell_schedule()

    assert schedule is not None
    assert schedule.is_sample is False
    assert notes == []


def test_a_real_file_wins_over_a_sample(bell_folder):
    _write(bell_folder, "a-sample.json", _schedule_data(sample=True, school="Sample"))
    _write(bell_folder, "our-bells.json", _schedule_data(school="Ours"))

    schedule, notes = loader.discover_bell_schedule()

    assert schedule.school == "Ours"
    assert schedule.is_sample is False
    assert notes == []


def test_only_samples_loads_one_and_says_so(bell_folder):
    _write(bell_folder, "one-sample.json", _schedule_data(sample=True))
    _write(bell_folder, "two-sample.json", _schedule_data(sample=True))

    schedule, notes = loader.discover_bell_schedule()

    assert schedule is not None
    assert schedule.is_sample is True
    assert any("sample" in note for note in notes)


def test_two_real_files_are_reported_rather_than_guessed_at(bell_folder):
    _write(bell_folder, "bells-a.json", _schedule_data(school="A"))
    _write(bell_folder, "bells-b.json", _schedule_data(school="B"))

    schedule, notes = loader.discover_bell_schedule()

    assert schedule is None
    joined = " ".join(notes)
    assert "bells-a.json" in joined
    assert "bells-b.json" in joined


def test_no_files_is_a_note_not_a_crash(bell_folder):
    schedule, notes = loader.discover_bell_schedule()

    assert schedule is None
    assert len(notes) == 1
    assert "Glass" in notes[0]
    assert str(bell_folder) in notes[0]


def test_missing_folder_is_a_note(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))

    schedule, notes = loader.discover_bell_schedule()

    assert schedule is None
    assert notes and "Glass" in notes[0]


def test_no_workspace_is_a_note(monkeypatch):
    monkeypatch.setattr(workspace, "workspace_root", lambda: None)

    assert loader.bell_schedule_folder() is None
    schedule, notes = loader.discover_bell_schedule()

    assert schedule is None
    assert notes and "workspace" in notes[0]


def test_a_section_map_in_the_folder_is_not_mistaken_for_a_schedule(bell_folder):
    _write(bell_folder, "our-bells.json", _schedule_data())
    _write(bell_folder, loader.SECTION_MAP_FILENAME, {
        "format": loader.SECTION_MAP_FORMAT,
        "sections": {"p4": {"course_id": "1", "section_name": "4th"}},
    })

    schedule, notes = loader.discover_bell_schedule()

    assert schedule is not None
    assert notes == []


def test_an_unrelated_json_file_is_skipped_with_a_note(bell_folder):
    _write(bell_folder, "our-bells.json", _schedule_data())
    _write(bell_folder, "notes.json", {"format": "something.else/1"})

    schedule, notes = loader.discover_bell_schedule()

    assert schedule is not None
    assert any("notes.json" in note for note in notes)


def test_broken_json_is_skipped_with_a_note(bell_folder):
    (bell_folder / "broken.json").write_text("{not json", encoding="utf-8")
    _write(bell_folder, "our-bells.json", _schedule_data())

    schedule, notes = loader.discover_bell_schedule()

    assert schedule is not None
    assert any("broken.json" in note for note in notes)


def test_an_unreadable_chosen_file_is_reported_not_raised(bell_folder):
    data = _schedule_data()
    del data["day_types"]["friday"]["blocks"][1]["start"]
    _write(bell_folder, "our-bells.json", data)

    schedule, notes = loader.discover_bell_schedule()

    assert schedule is None
    assert any("has no start time" in note for note in notes)


def test_structural_problems_are_surfaced_as_notes(bell_folder, monkeypatch):
    _write(bell_folder, "our-bells.json", _schedule_data())

    module = type(sys)("api.schedule.validate")
    module.validate = lambda schedule: ["4th Period sub-blocks leave a 5 minute gap"]
    monkeypatch.setitem(sys.modules, "api.schedule.validate", module)

    schedule, notes = loader.discover_bell_schedule()

    assert schedule is not None
    assert "4th Period sub-blocks leave a 5 minute gap" in notes


# ------------------------------------------------------------- section map


def test_section_map_loads_from_the_bell_schedules_folder(bell_folder):
    _write(bell_folder, loader.SECTION_MAP_FILENAME, {
        "format": loader.SECTION_MAP_FORMAT,
        "sections": {"p4": {"course_id": "4400", "section_name": "4th Period Reading"}},
    })

    section_map, notes = loader.load_section_map()

    assert notes == []
    assert section_map.sections["p4"].course_id == "4400"
    assert section_map.sections["p4"].section_name == "4th Period Reading"
    assert section_map.is_sample is False


def test_missing_section_map_is_optional(bell_folder):
    section_map, notes = loader.load_section_map()

    assert section_map is None
    assert notes and "optional" in notes[0]


def test_section_map_with_the_wrong_format_is_reported(bell_folder):
    _write(bell_folder, loader.SECTION_MAP_FILENAME, {
        "format": SCHEDULE_FORMAT, "sections": {},
    })

    section_map, notes = loader.load_section_map()

    assert section_map is None
    assert loader.SECTION_MAP_FORMAT in notes[0]


def test_section_map_entry_must_be_a_set_of_fields():
    with pytest.raises(loader.BellScheduleError) as err:
        loader.parse_section_map({
            "format": loader.SECTION_MAP_FORMAT,
            "sections": {"p4": "4th Period Reading"},
        })

    assert "p4" in str(err.value)
