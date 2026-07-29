"""One test per structural failure the validator has to catch.

The schedules here are invented, as is the school. They are built small on
purpose: each one carries exactly the mistake under test so a message can be
matched without guessing which problem produced it.
"""
from __future__ import annotations

from datetime import date, time

from api.schedule import validate
from api.schedule.models import BellSchedule, Block, DayType, SubBlocks

OVERRIDE_DAY = date(2027, 9, 21)


def _t(value: str) -> time:
    return time.fromisoformat(value)


def _block(
    block_id: str,
    start: str,
    end: str,
    *,
    kind: str = "class",
    sub_blocks: SubBlocks | None = None,
) -> Block:
    return Block(
        block_id=block_id,
        kind=kind,
        label=block_id.upper(),
        start=_t(start),
        end=_t(end),
        sub_blocks=sub_blocks,
    )


def _day(day_type_id: str, *blocks: Block) -> DayType:
    return DayType(
        day_type_id=day_type_id, label=day_type_id.title(), blocks=blocks
    )


def _sequential(*blocks: Block) -> SubBlocks:
    return SubBlocks(mode="sequential", blocks=blocks)


def _concurrent(*blocks: Block) -> SubBlocks:
    return SubBlocks(mode="concurrent", blocks=blocks)


def _schedule(*day_types: DayType, weekday_default=None, date_overrides=None):
    return BellSchedule(
        school="Riverstone Junior High",
        timezone="America/Chicago",
        day_types={day_type.day_type_id: day_type for day_type in day_types},
        weekday_default=weekday_default or {},
        date_overrides=date_overrides or {},
    )


def _clean_day_types() -> tuple[DayType, ...]:
    """All four day types, valid, as a baseline for the failure cases."""
    return (
        _day(
            "bobcat_hour",
            _block("p1", "08:10", "09:00"),
            _block("bobcat", "11:04", "12:04", kind="bobcat_hour",
                   sub_blocks=_concurrent()),
            _block("p5", "13:10", "14:00"),
        ),
        _day(
            "friday",
            _block("p1", "08:10", "09:00"),
            _block("p3", "10:06", "11:36", sub_blocks=_sequential(
                _block("p3a", "10:06", "10:51", kind="lunch"),
                _block("p3b", "10:51", "11:36", kind="lunch"),
            )),
        ),
        _day(
            "homeroom_first",
            _block("hr", "08:10", "08:30", kind="homeroom"),
            _block("p3", "10:18", "11:48", sub_blocks=_sequential(
                _block("p3a", "10:18", "11:03", kind="lunch"),
                _block("p3b", "11:03", "11:48", kind="lunch"),
            )),
        ),
        _day(
            "pep_rally",
            _block("p1", "08:10", "08:55"),
            _block("rally", "12:27", "13:12", kind="assembly"),
        ),
    )


def _clean_schedule() -> BellSchedule:
    return _schedule(
        *_clean_day_types(),
        weekday_default={0: "bobcat_hour", 4: "friday"},
        date_overrides={OVERRIDE_DAY: "homeroom_first"},
    )


def _matching(problems: list[str], needle: str) -> list[str]:
    return [problem for problem in problems if needle in problem]


def test_a_clean_schedule_reports_nothing():
    assert validate.validate(_clean_schedule()) == []


def test_weekday_default_naming_an_undefined_day_type():
    schedule = _schedule(
        *_clean_day_types(), weekday_default={0: "bobcat_hour", 2: "snow_day"}
    )

    problems = validate.validate(schedule)

    assert _matching(problems, "weekday_default[2]")
    assert _matching(problems, "snow_day")


def test_date_override_naming_an_undefined_day_type():
    schedule = _schedule(
        *_clean_day_types(), date_overrides={OVERRIDE_DAY: "field_trip"}
    )

    problems = validate.validate(schedule)

    assert _matching(problems, OVERRIDE_DAY.isoformat())
    assert _matching(problems, "field_trip")


def test_day_type_with_no_blocks():
    schedule = _schedule(_day("pep_rally"))

    problems = validate.validate(schedule)

    assert _matching(problems, "has no blocks")


def test_top_level_blocks_out_of_chronological_order():
    schedule = _schedule(_day(
        "friday",
        _block("p2", "09:08", "09:58"),
        _block("p1", "08:10", "09:00"),
    ))

    problems = validate.validate(schedule)

    assert _matching(problems, "out of chronological order")


def test_top_level_blocks_that_overlap():
    schedule = _schedule(_day(
        "friday",
        _block("p1", "08:10", "09:10"),
        _block("p2", "09:08", "09:58"),
    ))

    problems = validate.validate(schedule)

    assert _matching(problems, "overlap")


def test_block_that_does_not_end_after_it_starts():
    schedule = _schedule(_day("friday", _block("p1", "09:00", "08:10")))

    problems = validate.validate(schedule)

    assert _matching(problems, "not after its start")


def test_zero_length_block():
    schedule = _schedule(_day("friday", _block("p1", "09:00", "09:00")))

    assert _matching(validate.validate(schedule), "not after its start")


def test_sequential_sub_blocks_that_start_after_the_parent():
    schedule = _schedule(_day(
        "friday",
        _block("p3", "10:06", "11:36", sub_blocks=_sequential(
            _block("p3a", "10:10", "10:51", kind="lunch"),
            _block("p3b", "10:51", "11:36", kind="lunch"),
        )),
    ))

    problems = validate.validate(schedule)

    assert _matching(problems, "'p3a' starts at 10:10")


def test_sequential_sub_blocks_that_end_before_the_parent():
    schedule = _schedule(_day(
        "friday",
        _block("p3", "10:06", "11:36", sub_blocks=_sequential(
            _block("p3a", "10:06", "10:51", kind="lunch"),
            _block("p3b", "10:51", "11:30", kind="lunch"),
        )),
    ))

    problems = validate.validate(schedule)

    assert _matching(problems, "'p3b' ends at 11:30")


def test_sequential_sub_blocks_with_a_gap_between_them():
    schedule = _schedule(_day(
        "friday",
        _block("p3", "10:06", "11:36", sub_blocks=_sequential(
            _block("p3a", "10:06", "10:45", kind="lunch"),
            _block("p3b", "10:51", "11:36", kind="lunch"),
        )),
    ))

    problems = validate.validate(schedule)

    assert _matching(problems, "leaves a gap")


def test_sequential_sub_blocks_that_overlap_each_other():
    schedule = _schedule(_day(
        "friday",
        _block("p3", "10:06", "11:36", sub_blocks=_sequential(
            _block("p3a", "10:06", "10:55", kind="lunch"),
            _block("p3b", "10:51", "11:36", kind="lunch"),
        )),
    ))

    problems = validate.validate(schedule)

    assert _matching(problems, "overlap inside 'p3'")


def test_sequential_container_with_no_children():
    schedule = _schedule(_day(
        "friday", _block("p3", "10:06", "11:36", sub_blocks=_sequential()),
    ))

    problems = validate.validate(schedule)

    assert _matching(problems, "lists none")


def test_concurrent_offering_outside_the_parent_span():
    schedule = _schedule(_day(
        "bobcat_hour",
        _block("bobcat", "11:04", "12:04", kind="bobcat_hour",
               sub_blocks=_concurrent(
                   _block("club", "11:04", "12:30", kind="other"),
               )),
    ))

    problems = validate.validate(schedule)

    assert _matching(problems, "outside its parent")


def test_concurrent_container_with_an_internal_lunch_split():
    """Bobcat Hour is the lunch hour, so it never carries an A/B split."""
    schedule = _schedule(_day(
        "bobcat_hour",
        _block("bobcat", "11:04", "12:04", kind="bobcat_hour",
               sub_blocks=_concurrent(
                   _block("bobcat_a", "11:04", "11:34", kind="lunch"),
                   _block("bobcat_b", "11:34", "12:04", kind="lunch"),
               )),
    ))

    problems = validate.validate(schedule)

    assert _matching(problems, "has no A/B split")


def test_duplicate_block_ids_at_the_top_level():
    schedule = _schedule(_day(
        "friday",
        _block("p1", "08:10", "09:00"),
        _block("p1", "09:08", "09:58"),
    ))

    problems = validate.validate(schedule)

    assert _matching(problems, "more than once")


def test_duplicate_block_id_between_a_parent_and_its_child():
    schedule = _schedule(_day(
        "friday",
        _block("p3", "10:06", "11:36", sub_blocks=_sequential(
            _block("p3", "10:06", "10:51", kind="lunch"),
            _block("p3b", "10:51", "11:36", kind="lunch"),
        )),
    ))

    problems = validate.validate(schedule)

    assert _matching(problems, "block id 'p3' more than once")


def test_problems_name_the_day_type_they_came_from():
    schedule = _schedule(_day("pep_rally"), _day("friday"))

    problems = validate.validate(schedule)

    assert _matching(problems, "day type 'pep_rally'")
    assert _matching(problems, "day type 'friday'")
