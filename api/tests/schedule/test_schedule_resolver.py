"""Resolver tests against a wholly invented bell schedule.

Every time, label, and name below is fictional. No district schedule, calendar
date, club, tutorial, or section name goes in this repo, so the fixture is a
made-up school with made-up bells that happens to have the same shape as a real
one: four day types, one of which carries a lunch hour with simultaneous
offerings and three of which split a period into A and B lunch.

The fictional week used throughout is 2027-09-13 (Monday) to 2027-09-17
(Friday), with 2027-09-21 and 2027-09-22 carrying date overrides.
"""
from __future__ import annotations

from datetime import date, datetime, time

import pytest

from api.schedule import resolver
from api.schedule.models import BellSchedule, Block, DayType, SubBlocks

MONDAY = date(2027, 9, 13)
WEDNESDAY = date(2027, 9, 15)
THURSDAY = date(2027, 9, 16)
FRIDAY = date(2027, 9, 17)
SATURDAY = date(2027, 9, 18)
NEXT_MONDAY = date(2027, 9, 20)
HOMEROOM_FIRST_DAY = date(2027, 9, 21)
PEP_RALLY_DAY = date(2027, 9, 22)
NEXT_THURSDAY = date(2027, 9, 23)


def _t(value: str) -> time:
    return time.fromisoformat(value)


def _block(
    block_id: str,
    start: str,
    end: str,
    *,
    kind: str = "class",
    label: str | None = None,
    sub_blocks: SubBlocks | None = None,
    location: str = "",
) -> Block:
    return Block(
        block_id=block_id,
        kind=kind,
        label=label or block_id.upper(),
        start=_t(start),
        end=_t(end),
        sub_blocks=sub_blocks,
        location=location,
    )


def _ab_lunch(period: str, start: str, middle: str, end: str) -> SubBlocks:
    return SubBlocks(
        mode="sequential",
        blocks=(
            _block(f"{period}a", start, middle, kind="lunch",
                   label=f"{period.upper()} / A Lunch"),
            _block(f"{period}b", middle, end, kind="lunch",
                   label=f"{period.upper()} / B Lunch"),
        ),
    )


def _day(day_type_id: str, label: str, *blocks: Block) -> DayType:
    return DayType(day_type_id=day_type_id, label=label, blocks=blocks)


def _schedule() -> BellSchedule:
    bobcat_hour = _day(
        "bobcat_hour",
        "Bobcat Hour Day",
        _block("p1", "08:10", "09:00"),
        _block("p2", "09:08", "09:58"),
        _block("p3", "10:06", "10:56"),
        _block(
            "bobcat", "11:04", "12:04",
            kind="bobcat_hour",
            label="Bobcat Hour",
            sub_blocks=SubBlocks(mode="concurrent", blocks=()),
        ),
        _block("p4", "12:12", "13:02"),
        _block("p5", "13:10", "14:00"),
    )
    friday = _day(
        "friday",
        "Friday",
        _block("p1", "08:10", "09:00"),
        _block("p2", "09:08", "09:58"),
        _block("p3", "10:06", "11:36",
               sub_blocks=_ab_lunch("p3", "10:06", "10:51", "11:36")),
        _block("p4", "11:44", "12:34"),
        _block("p5", "12:42", "13:32"),
    )
    homeroom_first = _day(
        "homeroom_first",
        "Homeroom First",
        _block("hr", "08:10", "08:30", kind="homeroom", label="Homeroom"),
        _block("p1", "08:38", "09:20"),
        _block("p2", "09:28", "10:10"),
        _block("p3", "10:18", "11:48",
               sub_blocks=_ab_lunch("p3", "10:18", "11:03", "11:48")),
        _block("p4", "11:56", "12:38"),
        _block("p5", "12:46", "13:28"),
    )
    pep_rally = _day(
        "pep_rally",
        "Pep Rally",
        _block("p1", "08:10", "08:55"),
        _block("p2", "09:03", "09:48"),
        _block("p3", "09:56", "11:26",
               sub_blocks=_ab_lunch("p3", "09:56", "10:41", "11:26")),
        _block("p4", "11:34", "12:19"),
        _block("rally", "12:27", "13:12", kind="assembly", label="Pep Rally"),
        _block("p5", "13:20", "14:00"),
    )
    return BellSchedule(
        school="Riverstone Junior High",
        timezone="America/Chicago",
        day_types={
            "bobcat_hour": bobcat_hour,
            "friday": friday,
            "homeroom_first": homeroom_first,
            "pep_rally": pep_rally,
        },
        weekday_default={0: "bobcat_hour", 1: "bobcat_hour", 2: "bobcat_hour",
                         3: "bobcat_hour", 4: "friday"},
        date_overrides={
            HOMEROOM_FIRST_DAY: "homeroom_first",
            PEP_RALLY_DAY: "pep_rally",
        },
    )


@pytest.fixture
def schedule() -> BellSchedule:
    return _schedule()


def _at(day: date, clock: str) -> datetime:
    return datetime.combine(day, _t(clock))


# Each day type, the date it falls on in the fictional week, and its first block.
DAY_TYPES = [
    ("bobcat_hour", WEDNESDAY, "p1", "08:10", 50),
    ("friday", FRIDAY, "p1", "08:10", 50),
    ("homeroom_first", HOMEROOM_FIRST_DAY, "hr", "08:10", 20),
    ("pep_rally", PEP_RALLY_DAY, "p1", "08:10", 45),
]


@pytest.mark.parametrize("day_type_id,day,block_id,start,minutes", DAY_TYPES)
def test_first_bell_lands_in_the_first_block(
    schedule, day_type_id, day, block_id, start, minutes
):
    got = resolver.resolve(schedule, _at(day, start))

    assert got.placement == "in_block"
    assert got.day_type is not None and got.day_type.day_type_id == day_type_id
    assert got.block is not None and got.block.block_id == block_id
    assert got.elapsed_minutes == 0
    assert got.remaining_minutes == minutes
    assert got.percent_complete == 0.0


# A mid-block moment per day type, with the numbers the rail should show.
MID_BLOCK = [
    ("bobcat_hour", WEDNESDAY, "09:30", "p2", 22, 28),
    ("friday", FRIDAY, "08:35", "p1", 25, 25),
    ("homeroom_first", HOMEROOM_FIRST_DAY, "08:20", "hr", 10, 10),
    ("pep_rally", PEP_RALLY_DAY, "08:33", "p1", 23, 22),
]


@pytest.mark.parametrize("day_type_id,day,clock,block_id,elapsed,remaining", MID_BLOCK)
def test_mid_block_reports_elapsed_and_remaining(
    schedule, day_type_id, day, clock, block_id, elapsed, remaining
):
    got = resolver.resolve(schedule, _at(day, clock))

    assert got.placement == "in_block"
    assert got.day_type is not None and got.day_type.day_type_id == day_type_id
    assert got.block is not None and got.block.block_id == block_id
    assert (got.elapsed_minutes, got.remaining_minutes) == (elapsed, remaining)
    assert 0.0 <= got.percent_complete <= 1.0


def test_mid_block_percent_is_the_fraction_of_the_block(schedule):
    got = resolver.resolve(schedule, _at(FRIDAY, "08:35"))

    assert got.percent_complete == pytest.approx(0.5)


# Both sides of one passing period per day type: the last minute of the
# outgoing block, the gap itself, and the first minute of the incoming block.
PASSING = [
    ("bobcat_hour", WEDNESDAY, "08:59", "p1", "09:04", "p2", "09:08"),
    ("friday", FRIDAY, "08:59", "p1", "09:04", "p2", "09:08"),
    ("homeroom_first", HOMEROOM_FIRST_DAY, "08:29", "hr", "08:34", "p1", "08:38"),
    ("pep_rally", PEP_RALLY_DAY, "08:54", "p1", "08:59", "p2", "09:03"),
]


@pytest.mark.parametrize(
    "day_type_id,day,before,before_id,gap,after_id,after", PASSING
)
def test_both_sides_of_a_passing_period(
    schedule, day_type_id, day, before, before_id, gap, after_id, after
):
    still_in_class = resolver.resolve(schedule, _at(day, before))
    assert still_in_class.placement == "in_block"
    assert still_in_class.block is not None
    assert still_in_class.block.block_id == before_id
    assert still_in_class.next_block is not None
    assert still_in_class.next_block.block_id == after_id

    between = resolver.resolve(schedule, _at(day, gap))
    assert between.placement == "passing"
    assert between.block is None
    assert between.next_block is not None
    assert between.next_block.block_id == after_id
    assert between.remaining_minutes > 0
    assert 0.0 < between.percent_complete < 1.0

    next_class = resolver.resolve(schedule, _at(day, after))
    assert next_class.placement == "in_block"
    assert next_class.block is not None
    assert next_class.block.block_id == after_id
    assert next_class.elapsed_minutes == 0


def test_passing_counts_down_to_the_next_bell(schedule):
    got = resolver.resolve(schedule, _at(WEDNESDAY, "09:04"))

    assert (got.elapsed_minutes, got.remaining_minutes) == (4, 4)
    assert got.percent_complete == pytest.approx(0.5)
    assert got.current_label == "Passing"


@pytest.mark.parametrize("day_type_id,day,block_id,start,minutes", DAY_TYPES)
def test_before_school(schedule, day_type_id, day, block_id, start, minutes):
    got = resolver.resolve(schedule, _at(day, "07:30"))

    assert got.placement == "before_school"
    assert got.day_type is not None and got.day_type.day_type_id == day_type_id
    assert got.block is None
    assert got.next_block is not None and got.next_block.block_id == block_id
    assert got.remaining_minutes == 40
    assert got.percent_complete == 0.0
    assert got.current_label == "Before school"


# The last bell of each day type, which is also the first moment of after school.
LAST_BELL = [
    ("bobcat_hour", WEDNESDAY, "14:00"),
    ("friday", FRIDAY, "13:32"),
    ("homeroom_first", HOMEROOM_FIRST_DAY, "13:28"),
    ("pep_rally", PEP_RALLY_DAY, "14:00"),
]


@pytest.mark.parametrize("day_type_id,day,last_bell", LAST_BELL)
def test_after_school_starts_at_the_last_bell(schedule, day_type_id, day, last_bell):
    at_the_bell = resolver.resolve(schedule, _at(day, last_bell))
    assert at_the_bell.placement == "after_school"
    assert at_the_bell.day_type is not None
    assert at_the_bell.day_type.day_type_id == day_type_id
    assert at_the_bell.block is None
    assert at_the_bell.next_block is None
    assert at_the_bell.percent_complete == 0.0
    assert at_the_bell.current_label == "After school"

    later = resolver.resolve(schedule, _at(day, "16:45"))
    assert later.placement == "after_school"


# The A/B lunch split, which only the three non-Bobcat-Hour day types carry.
LUNCH_SPLIT = [
    ("friday", FRIDAY, "p3", "10:20", "p3a", 14, 31, "11:10", "p3b", 19, 26),
    ("homeroom_first", HOMEROOM_FIRST_DAY, "p3", "10:30", "p3a", 12, 33,
     "11:20", "p3b", 17, 28),
    ("pep_rally", PEP_RALLY_DAY, "p3", "10:10", "p3a", 14, 31,
     "11:00", "p3b", 19, 26),
]


@pytest.mark.parametrize(
    "day_type_id,day,parent_id,a_clock,a_id,a_elapsed,a_remaining,"
    "b_clock,b_id,b_elapsed,b_remaining",
    LUNCH_SPLIT,
)
def test_both_sides_of_the_lunch_split(
    schedule, day_type_id, day, parent_id, a_clock, a_id, a_elapsed, a_remaining,
    b_clock, b_id, b_elapsed, b_remaining,
):
    a_side = resolver.resolve(schedule, _at(day, a_clock))
    assert a_side.placement == "in_block"
    assert a_side.block is not None and a_side.block.block_id == parent_id
    assert a_side.sub_block is not None and a_side.sub_block.block_id == a_id
    # Measured across the sub-block, not the parent double period.
    assert (a_side.elapsed_minutes, a_side.remaining_minutes) == (a_elapsed, a_remaining)
    assert a_side.current_label == a_side.sub_block.label

    b_side = resolver.resolve(schedule, _at(day, b_clock))
    assert b_side.block is not None and b_side.block.block_id == parent_id
    assert b_side.sub_block is not None and b_side.sub_block.block_id == b_id
    assert (b_side.elapsed_minutes, b_side.remaining_minutes) == (b_elapsed, b_remaining)


def test_bobcat_hour_has_no_internal_lunch_split(schedule):
    got = resolver.resolve(schedule, _at(WEDNESDAY, "11:34"))

    assert got.block is not None and got.block.block_id == "bobcat"
    assert got.sub_block is None
    assert got.block.offerings == ()
    # Measured across the whole hour, since there is no sub-block to be in.
    assert (got.elapsed_minutes, got.remaining_minutes) == (30, 30)


def test_weekend_is_no_school(schedule):
    got = resolver.resolve(schedule, _at(SATURDAY, "10:00"))

    assert got.placement == "no_school"
    assert got.is_school_day is False
    assert got.day_type is None
    assert got.current_label == "No school"


def test_calendar_no_school_date_beats_the_weekly_pattern(schedule):
    got = resolver.resolve(
        schedule, _at(WEDNESDAY, "10:00"), no_school_dates=frozenset({WEDNESDAY})
    )

    assert got.placement == "no_school"
    assert got.block is None


def test_same_day_override_changes_the_day_type_without_touching_the_calendar(schedule):
    before = dict(schedule.date_overrides)

    without = resolver.resolve(schedule, _at(WEDNESDAY, "10:00"))
    assert without.day_type is not None
    assert without.day_type.day_type_id == "bobcat_hour"
    assert without.placement == "passing"

    with_override = resolver.resolve(
        schedule, _at(WEDNESDAY, "10:00"), override="pep_rally"
    )
    assert with_override.day_type is not None
    assert with_override.day_type.day_type_id == "pep_rally"
    assert with_override.placement == "in_block"
    assert with_override.block is not None
    assert with_override.block.block_id == "p3"
    assert with_override.sub_block is not None
    assert with_override.sub_block.block_id == "p3a"

    assert dict(schedule.date_overrides) == before
    assert WEDNESDAY not in schedule.date_overrides


def test_same_day_override_beats_a_date_override(schedule):
    got = resolver.resolve(
        schedule, _at(PEP_RALLY_DAY, "08:20"), override="homeroom_first"
    )

    assert got.day_type is not None
    assert got.day_type.day_type_id == "homeroom_first"
    assert got.block is not None and got.block.block_id == "hr"


def test_unknown_override_is_an_error(schedule):
    with pytest.raises(ValueError) as caught:
        resolver.resolve(schedule, _at(WEDNESDAY, "10:00"), override="snow_day")

    assert "snow_day" in str(caught.value)


def test_override_does_not_un_cancel_a_no_school_date(schedule):
    got = resolver.resolve(
        schedule,
        _at(WEDNESDAY, "10:00"),
        no_school_dates=frozenset({WEDNESDAY}),
        override="pep_rally",
    )

    assert got.placement == "no_school"


def test_next_bobcat_hour_from_wednesday_morning_is_today(schedule):
    got = resolver.next_occurrence(schedule, _at(WEDNESDAY, "08:30"), "bobcat_hour")

    assert got is not None
    assert got.on == WEDNESDAY
    assert got.is_today is True
    assert got.block.block_id == "bobcat"
    assert got.day_type.day_type_id == "bobcat_hour"


def test_next_bobcat_hour_while_it_is_running_is_still_today(schedule):
    got = resolver.next_occurrence(schedule, _at(WEDNESDAY, "12:03"), "bobcat_hour")

    assert got is not None and got.on == WEDNESDAY and got.is_today is True


def test_next_bobcat_hour_after_it_ends_is_tomorrow(schedule):
    got = resolver.next_occurrence(schedule, _at(WEDNESDAY, "12:30"), "bobcat_hour")

    assert got is not None
    assert got.on == THURSDAY
    assert got.is_today is False
    assert got.block.block_id == "bobcat"


@pytest.mark.parametrize("clock", ["07:00", "11:30", "16:00"])
def test_next_bobcat_hour_from_a_friday_is_the_following_monday(schedule, clock):
    got = resolver.next_occurrence(schedule, _at(FRIDAY, clock), "bobcat_hour")

    assert got is not None
    assert got.on == NEXT_MONDAY
    assert got.is_today is False
    assert got.day_type.day_type_id == "bobcat_hour"


def test_next_bobcat_hour_from_a_pep_rally_day_skips_that_day(schedule):
    got = resolver.next_occurrence(schedule, _at(PEP_RALLY_DAY, "08:30"), "bobcat_hour")

    assert got is not None
    assert got.on == NEXT_THURSDAY
    assert got.is_today is False


def test_next_bobcat_hour_skips_a_calendar_no_school_date(schedule):
    got = resolver.next_occurrence(
        schedule,
        _at(WEDNESDAY, "12:30"),
        "bobcat_hour",
        no_school_dates=frozenset({THURSDAY}),
    )

    assert got is not None
    # Thursday is out, Friday carries no Bobcat Hour, so it lands on Monday.
    assert got.on == NEXT_MONDAY
    assert got.is_today is False


def test_next_bobcat_hour_from_a_weekend_is_monday(schedule):
    got = resolver.next_occurrence(schedule, _at(SATURDAY, "09:00"), "bobcat_hour")

    assert got is not None and got.on == NEXT_MONDAY and got.is_today is False


def test_next_occurrence_applies_a_same_day_override_only_to_today(schedule):
    overridden = resolver.next_occurrence(
        schedule, _at(WEDNESDAY, "08:30"), "bobcat_hour", override="pep_rally"
    )
    assert overridden is not None
    assert overridden.on == THURSDAY

    borrowed = resolver.next_occurrence(
        schedule, _at(FRIDAY, "08:30"), "bobcat_hour", override="bobcat_hour"
    )
    assert borrowed is not None
    assert borrowed.on == FRIDAY
    assert borrowed.is_today is True


def test_next_occurrence_finds_an_assembly_two_weeks_out(schedule):
    got = resolver.next_occurrence(schedule, _at(MONDAY, "08:00"), "assembly")

    assert got is not None
    assert got.on == PEP_RALLY_DAY
    assert got.block.block_id == "rally"


def test_next_occurrence_returns_none_outside_the_search_window(schedule):
    got = resolver.next_occurrence(
        schedule, _at(FRIDAY, "08:30"), "bobcat_hour", search_days=2
    )

    assert got is None


def test_next_occurrence_returns_none_for_a_kind_nobody_runs(schedule):
    assert resolver.next_occurrence(schedule, _at(MONDAY, "08:00"), "advisory") is None


def test_resolve_never_reads_the_clock(schedule):
    """Two calls with the same instant must agree, whatever time it is here."""
    first = resolver.resolve(schedule, _at(WEDNESDAY, "09:30"))
    second = resolver.resolve(schedule, _at(WEDNESDAY, "09:30"))

    assert first == second
