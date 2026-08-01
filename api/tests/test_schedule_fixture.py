"""Resolve a complete alternating-day schedule from its on-disk fixtures."""

import csv
import io
import json
from datetime import date
from pathlib import Path

import pytest

from api.webui import deck_schedule
from api.webui.deps import _file_key


FIXTURE = Path(__file__).parent / "fixtures" / "class_schedule"
BELL_FILES = [
    "Bell Schedule - Example Day A.csv",
    "Bell Schedule - Example Day B.csv",
    "Bell Schedule - Example Short Day.csv",
]
SCHEDULE_MAP_FILE = "Schedule Map - Example Alternating Day Split.csv"
MONDAY = "2026-08-17"
TUESDAY = "2026-08-18"
WEDNESDAY = "2026-08-19"
THURSDAY = "2026-08-20"
FRIDAY = "2026-08-21"
SECOND_SHORT_DAY = "2026-08-27"
ALL_CHECK_DATES = [MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SECOND_SHORT_DAY]


def _read_fixture_schedule_map(content: str) -> dict:
    """A tiny local reader for the fixture's date,schedule_id CSV.

    This test-only map is a convenient way to express which schedule applies
    on each date without making the pure schedule resolver read workspace data.
    """
    mapping = {}
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        mapping[date.fromisoformat(row["date"]).isoformat()] = row["schedule_id"]
    return mapping


@pytest.fixture(scope="module")
def schedule():
    teacher = json.loads((FIXTURE / "Teacher Schedule.json").read_text(encoding="utf-8"))
    bell = {}
    for filename in BELL_FILES:
        meetings, problems = deck_schedule.parse_bell_schedule(
            (FIXTURE / filename).read_text(encoding="utf-8")
        )
        assert problems == [], f"{filename}: {problems}"
        bell[_file_key(filename)] = meetings

    day_calendar = _read_fixture_schedule_map(
        (FIXTURE / SCHEDULE_MAP_FILE).read_text(encoding="utf-8")
    )
    return teacher, bell, day_calendar


def _names(blocks):
    return {block["name"] for block in blocks}


def test_the_fixture_schedule_validates(schedule):
    teacher, _bell, _day_calendar = schedule
    assert deck_schedule.validate_teacher_schedule(teacher) == []


def test_every_day_calendar_schedule_id_has_a_bell_schedule(schedule):
    _teacher, bell, day_calendar = schedule
    assert set(day_calendar.values()) <= set(bell)


def test_the_day_calendar_covers_weekdays_only_and_skips_the_holiday(schedule):
    _teacher, _bell, day_calendar = schedule
    assert day_calendar
    assert all(date.fromisoformat(value).weekday() < 5 for value in day_calendar)
    assert "2026-09-07" not in day_calendar


@pytest.mark.parametrize("check_date", ALL_CHECK_DATES)
def test_resolves_with_zero_problems(schedule, check_date):
    teacher, bell, day_calendar = schedule
    blocks, problems = deck_schedule.resolve_day(day_calendar[check_date], bell, teacher)
    assert problems == []
    assert blocks


def test_day_a_and_day_b_resolve_different_class_sets(schedule):
    teacher, bell, day_calendar = schedule
    day_a = _names(deck_schedule.resolve_day(day_calendar[MONDAY], bell, teacher)[0])
    day_b = _names(deck_schedule.resolve_day(day_calendar[TUESDAY], bell, teacher)[0])
    assert day_a != day_b


def test_short_day_resolves_the_same_class_set_on_different_weekdays(schedule):
    teacher, bell, day_calendar = schedule
    friday = _names(deck_schedule.resolve_day(day_calendar[FRIDAY], bell, teacher)[0])
    wednesday = _names(
        deck_schedule.resolve_day(day_calendar[SECOND_SHORT_DAY], bell, teacher)[0]
    )
    assert friday == wednesday
    assert len(friday) == 8


def test_short_day_is_not_assumed_to_be_friday(schedule):
    _teacher, _bell, day_calendar = schedule
    assert day_calendar[SECOND_SHORT_DAY] == "bell_schedule_example_short_day"
    assert date.fromisoformat(SECOND_SHORT_DAY).weekday() == 3
