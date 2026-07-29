"""Where a given instant falls in the school day.

Pure by design: no clock read, no file read, no calendar lookup. The instant
arrives as a parameter and no-school dates arrive as a set, which is what makes
a frozen clock possible for the caller and makes every state here testable
without waiting for 12:13 to come around.

Two conventions worth stating once, because a rail on a wall reads them all day:

* **Measured span.** When a period splits into A and B lunch, elapsed and
  remaining are measured across the active sub-block, not the parent period.
  The screen counts down the thing the students are actually in, so a student in
  A lunch sees A lunch ending, not the whole double period.
* **Rounding.** Remaining minutes round up and elapsed minutes round down, so a
  rail never shows "0 min" while a class is still in session and never claims a
  minute that has not finished.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from .models import BellSchedule, Block, BlockKind, DayType, NextOccurrence, Resolved


def resolve(
    schedule: BellSchedule,
    at: datetime,
    *,
    no_school_dates: frozenset[date] = frozenset(),
    override: str | None = None,
) -> Resolved:
    """Resolve a single instant against the schedule.

    `override` is the same-day day-type change that arrives by email before
    first bell. It beats `date_overrides` and `weekday_default` and needs no
    edit to any file. It names a day type, though, so it does not un-cancel a
    date the academic calendar reports as non-instructional; a holiday stays a
    holiday.

    Raises ValueError when `override` names a day type the schedule does not
    define. Silently falling back would put a normal day on the screen on a day
    the teacher explicitly said was not normal.
    """
    _check_override(schedule, override)
    day = at.date()

    if day in no_school_dates:
        return Resolved(at=at, placement="no_school")

    day_type = _day_type_for(schedule, day, override=override, is_today=True)
    if day_type is None or not day_type.blocks:
        return Resolved(at=at, placement="no_school", day_type=day_type)

    blocks = day_type.blocks
    now = at.time()
    first, last = blocks[0], blocks[-1]

    if now < first.start:
        # Remaining counts down to first bell, which is what the rail wants
        # before school. There is no span to be a fraction of, so percent is 0.
        return Resolved(
            at=at,
            placement="before_school",
            day_type=day_type,
            next_block=first,
            remaining_minutes=_minutes_up(_gap_seconds(now, first.start)),
        )

    if now >= last.end:
        return Resolved(at=at, placement="after_school", day_type=day_type)

    for index, block in enumerate(blocks):
        if block.contains(now):
            return _in_block(at, day_type, blocks, index, block, now)

    return _passing(at, day_type, blocks, now)


def next_occurrence(
    schedule: BellSchedule,
    at: datetime,
    kind: BlockKind,
    *,
    no_school_dates: frozenset[date] = frozenset(),
    override: str | None = None,
    search_days: int = 14,
) -> NextOccurrence | None:
    """The next block of this kind that has not ended yet, and its date.

    Today counts while the block is still running, which is why the Bobcat Hour
    panel can show today's offerings up to the last minute and flip to tomorrow
    on its own. Day types without the block are skipped, so a Friday resolves
    forward to Monday rather than reporting nothing.

    `override` applies to `at.date()` only. A same-day change says nothing about
    what next Tuesday looks like.

    Searches `search_days` calendar days including today and returns None when
    the kind never comes up in that window.
    """
    _check_override(schedule, override)

    for offset in range(max(search_days, 0)):
        day = at.date() + timedelta(days=offset)
        if day in no_school_dates:
            continue
        is_today = offset == 0
        day_type = _day_type_for(schedule, day, override=override, is_today=is_today)
        if day_type is None:
            continue
        block = day_type.first_of_kind(kind)
        if block is None:
            continue
        if is_today and at.time() >= block.end:
            continue
        return NextOccurrence(
            on=day, day_type=day_type, block=block, is_today=is_today
        )
    return None


def _check_override(schedule: BellSchedule, override: str | None) -> None:
    if override is not None and override not in schedule.day_types:
        raise ValueError(
            f"same-day override names day type '{override}', which this "
            f"schedule does not define"
        )


def _day_type_for(
    schedule: BellSchedule, day: date, *, override: str | None, is_today: bool
) -> DayType | None:
    if override is not None and is_today:
        return schedule.day_type(override)
    return schedule.day_type(schedule.day_type_id_for(day))


def _in_block(
    at: datetime,
    day_type: DayType,
    blocks: tuple[Block, ...],
    index: int,
    block: Block,
    now: time,
) -> Resolved:
    sub_block = block.active_sub_block(now)
    span = sub_block if sub_block is not None else block
    next_block = blocks[index + 1] if index + 1 < len(blocks) else None

    elapsed = _gap_seconds(span.start, now)
    remaining = _gap_seconds(now, span.end)
    return Resolved(
        at=at,
        placement="in_block",
        day_type=day_type,
        block=block,
        sub_block=sub_block,
        next_block=next_block,
        elapsed_minutes=_minutes_down(elapsed),
        remaining_minutes=_minutes_up(remaining),
        percent_complete=_fraction(elapsed, elapsed + remaining),
    )


def _passing(
    at: datetime, day_type: DayType, blocks: tuple[Block, ...], now: time
) -> Resolved:
    """The gap between two blocks.

    Passing periods are not blocks, so there is nothing to report as current.
    Remaining counts down to the next bell and percent runs across the gap,
    which is what drives the between-classes state on the screen.
    """
    previous = blocks[0]
    upcoming = blocks[-1]
    for earlier, later in zip(blocks, blocks[1:]):
        if earlier.end <= now < later.start:
            previous, upcoming = earlier, later
            break

    elapsed = _gap_seconds(previous.end, now)
    remaining = _gap_seconds(now, upcoming.start)
    return Resolved(
        at=at,
        placement="passing",
        day_type=day_type,
        next_block=upcoming,
        elapsed_minutes=_minutes_down(elapsed),
        remaining_minutes=_minutes_up(remaining),
        percent_complete=_fraction(elapsed, elapsed + remaining),
    )


def _seconds(t: time) -> int:
    return t.hour * 3600 + t.minute * 60 + t.second


def _gap_seconds(start: time, end: time) -> int:
    return max(_seconds(end) - _seconds(start), 0)


def _minutes_down(seconds: int) -> int:
    return seconds // 60


def _minutes_up(seconds: int) -> int:
    return -(-seconds // 60)


def _fraction(part: int, whole: int) -> float:
    if whole <= 0:
        return 0.0
    return min(max(part / whole, 0.0), 1.0)
