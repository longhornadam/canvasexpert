"""Resolve a full multi-schedule week against a realistic on-disk schedule.

`test_deck_schedule.py` covers `resolve_day` with inline literals, one behavior at a
time. This file is the other half: one complete schedule read from files, exercised
across a whole week, so the pieces are proven to compose. It catches what a unit test
by construction cannot, namely a weekday split and a day-type switch interacting on
the same date.

The fixture is a teaching schedule with invented courses and bell times: Monday and
Wednesday carry one set of classes, Tuesday and Thursday another, Friday is a short day
where every class meets once, and 2026-09-02 is an assembly day. Its `schedule_id`
values derive from its bell schedule filenames through `_file_key`, so renaming a
fixture file breaks resolution the same way it would in a real workspace.
"""

from datetime import date
from pathlib import Path

import json
import pytest

from api.webui import deck_schedule
from api.webui.routes.calendar import _file_key


FIXTURE = Path(__file__).parent / "fixtures" / "class_schedule"
BELL_FILES = [
    "Bell Schedule - Example Split Day.csv",
    "Bell Schedule - Example Split Friday.csv",
    "Bell Schedule - Example Split Assembly.csv",
]
DAY_CALENDAR_FILE = "Day Calendar - Example Alternating Day Split.csv"
MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY = (
    "2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21",
)
ASSEMBLY_WEDNESDAY = "2026-09-02"
ALL_CHECK_DATES = [MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, ASSEMBLY_WEDNESDAY]


@pytest.fixture(scope="module")
def schedule():
    """(teacher_schedule, bell_schedules, day_calendar) parsed from the fixture files."""
    teacher = json.loads((FIXTURE / "Teacher Schedule.json").read_text(encoding="utf-8"))

    bell = {}
    for filename in BELL_FILES:
        periods, problems = deck_schedule.parse_bell_schedule(
            (FIXTURE / filename).read_text(encoding="utf-8")
        )
        assert problems == [], f"{filename}: {problems}"
        bell[_file_key(filename)] = periods

    day_calendar, problems = deck_schedule.parse_day_calendar(
        (FIXTURE / DAY_CALENDAR_FILE).read_text(encoding="utf-8")
    )
    assert problems == [], problems
    return teacher, bell, day_calendar


def _names(blocks):
    return {block["name"] for block in blocks}


def test_the_fixture_schedule_validates(schedule):
    teacher, _bell, _day_calendar = schedule
    assert deck_schedule.validate_teacher_schedule(teacher) == []


def test_every_day_calendar_schedule_id_has_a_bell_schedule(schedule):
    _teacher, bell, day_calendar = schedule
    assert set(day_calendar.values()) <= set(bell)


def test_the_day_calendar_covers_weekdays_only_and_skips_the_september_holiday(schedule):
    _teacher, _bell, day_calendar = schedule
    assert day_calendar
    assert all(date.fromisoformat(value).weekday() < 5 for value in day_calendar)
    assert "2026-09-07" not in day_calendar, "a no-school day is expressed by omitting the date"


@pytest.mark.parametrize("check_date", ALL_CHECK_DATES)
def test_resolves_with_zero_problems(schedule, check_date):
    """A block that does not meet today is silently absent, never a warning."""
    teacher, bell, day_calendar = schedule
    blocks, problems = deck_schedule.resolve_day(check_date, day_calendar, bell, teacher)
    assert problems == []
    assert blocks


def test_each_weekday_family_resolves_a_different_block_set(schedule):
    teacher, bell, day_calendar = schedule
    monday = _names(deck_schedule.resolve_day(MONDAY, day_calendar, bell, teacher)[0])
    tuesday = _names(deck_schedule.resolve_day(TUESDAY, day_calendar, bell, teacher)[0])
    friday = _names(deck_schedule.resolve_day(FRIDAY, day_calendar, bell, teacher)[0])
    assert monday != tuesday
    assert monday != friday
    assert tuesday != friday


def test_monday_and_wednesday_resolve_the_same_block_set(schedule):
    teacher, bell, day_calendar = schedule
    monday = _names(deck_schedule.resolve_day(MONDAY, day_calendar, bell, teacher)[0])
    wednesday = _names(deck_schedule.resolve_day(WEDNESDAY, day_calendar, bell, teacher)[0])
    assert monday == wednesday


def test_tuesday_and_thursday_resolve_the_same_block_set(schedule):
    teacher, bell, day_calendar = schedule
    tuesday = _names(deck_schedule.resolve_day(TUESDAY, day_calendar, bell, teacher)[0])
    thursday = _names(deck_schedule.resolve_day(THURSDAY, day_calendar, bell, teacher)[0])
    assert tuesday == thursday


def test_a_shared_block_name_resolves_on_both_of_its_weekday_sets(schedule):
    """Two blocks may share a name when their weekdays are disjoint.

    This is what lets a slide bound to one name work on a Monday and on the short
    Friday schedule, at different periods and different times.
    """
    teacher, bell, day_calendar = schedule
    monday, _ = deck_schedule.resolve_day(MONDAY, day_calendar, bell, teacher)
    friday, _ = deck_schedule.resolve_day(FRIDAY, day_calendar, bell, teacher)
    shared = (_names(monday) - {"Planning"}) & _names(friday)
    assert shared, "expected at least one course to meet on both day types"

    for name in shared:
        monday_block = next(block for block in monday if block["name"] == name)
        friday_block = next(block for block in friday if block["name"] == name)
        monday_window = (monday_block["start"], monday_block["end"])
        friday_window = (friday_block["start"], friday_block["end"])
        assert monday_window != friday_window, (
            f"{name} should sit in a different window on the short Friday schedule"
        )


def test_the_weekday_split_and_the_day_type_compose(schedule):
    """The weekday picks which classes; the bell schedule picks the clock."""
    teacher, bell, day_calendar = schedule
    wednesday, _ = deck_schedule.resolve_day(WEDNESDAY, day_calendar, bell, teacher)
    assembly, _ = deck_schedule.resolve_day(ASSEMBLY_WEDNESDAY, day_calendar, bell, teacher)

    assert _names(wednesday) == _names(assembly), "same weekday, so the same classes"
    times = {block["name"]: (block["start"], block["end"]) for block in wednesday}
    assert any(
        times[block["name"]] != (block["start"], block["end"]) for block in assembly
    ), "the assembly day should move at least one block's clock time"
