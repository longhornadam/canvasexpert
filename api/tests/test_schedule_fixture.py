"""Resolve a complete alternating-day schedule from its on-disk fixtures."""

import json
from datetime import date
from pathlib import Path

import pytest

from api.webui import deck_schedule
from api.webui.routes.calendar import _file_key


FIXTURE = Path(__file__).parent / "fixtures" / "class_schedule"
BELL_FILES = [
    "Bell Schedule - Example Day A.csv",
    "Bell Schedule - Example Day B.csv",
    "Bell Schedule - Example Short Day.csv",
]
DAY_CALENDAR_FILE = "Day Calendar - Example Alternating Day Split.csv"
MONDAY = "2026-08-17"
TUESDAY = "2026-08-18"
WEDNESDAY = "2026-08-19"
THURSDAY = "2026-08-20"
FRIDAY = "2026-08-21"
SECOND_SHORT_DAY = "2026-08-27"
ALL_CHECK_DATES = [MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SECOND_SHORT_DAY]


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


def test_the_day_calendar_covers_weekdays_only_and_skips_the_holiday(schedule):
    _teacher, _bell, day_calendar = schedule
    assert day_calendar
    assert all(date.fromisoformat(value).weekday() < 5 for value in day_calendar)
    assert "2026-09-07" not in day_calendar


@pytest.mark.parametrize("check_date", ALL_CHECK_DATES)
def test_resolves_with_zero_problems(schedule, check_date):
    teacher, bell, day_calendar = schedule
    blocks, problems = deck_schedule.resolve_day(check_date, day_calendar, bell, teacher)
    assert problems == []
    assert blocks


def test_day_a_and_day_b_resolve_different_class_sets(schedule):
    teacher, bell, day_calendar = schedule
    day_a = _names(deck_schedule.resolve_day(MONDAY, day_calendar, bell, teacher)[0])
    day_b = _names(deck_schedule.resolve_day(TUESDAY, day_calendar, bell, teacher)[0])
    assert day_a != day_b


def test_short_day_resolves_the_same_class_set_on_different_weekdays(schedule):
    teacher, bell, day_calendar = schedule
    friday = _names(deck_schedule.resolve_day(FRIDAY, day_calendar, bell, teacher)[0])
    wednesday = _names(
        deck_schedule.resolve_day(SECOND_SHORT_DAY, day_calendar, bell, teacher)[0]
    )
    assert friday == wednesday
    assert len(friday) == 8


def test_short_day_is_not_assumed_to_be_friday(schedule):
    _teacher, _bell, day_calendar = schedule
    assert day_calendar[SECOND_SHORT_DAY] == "bell_schedule_example_short_day"
    assert date.fromisoformat(SECOND_SHORT_DAY).weekday() == 3
