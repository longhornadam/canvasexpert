"""The shape of a school day: blocks, day types, and a resolved moment.

This module is the standardised format the rest of the schedule work is built
on, so it holds no I/O, no clock, and no notion of a projector. It is
CE-general on purpose -- "which section is in the room right now" is useful
outside Glass -- so nothing here imports Glass and Glass is only its first
consumer.

Two vocabulary notes, both worth keeping straight:

* A "block" here is a stretch of the bell schedule. It is not a Canvas grading
  period; `api/webui/config/calendars.py` already uses "grading_periods" for
  report-card windows, and the two must not be confused.
* Passing periods are not blocks. They are the gaps between blocks, and the
  resolver reports them as a placement rather than as an entry in the day.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Iterator, Literal, Mapping

SCHEDULE_FORMAT = "canvasexpert.bell_schedule/1"

BlockKind = Literal[
    "class", "homeroom", "bobcat_hour", "lunch", "advisory", "assembly", "other",
]

# How a container block's children relate to it.
#
#   sequential -- the children partition the parent's time end to end. This is
#                 A/B lunch inside a period on a Friday, Homeroom First, or Pep
#                 Rally day: the children are sub-blocks of the parent period,
#                 not peers of it.
#   concurrent -- the children all run for the parent's whole span and carry a
#                 label and a location. This is Bobcat Hour's simultaneous
#                 offerings. They do not partition anything, and a concurrent
#                 parent has no internal lunch split.
SubBlockMode = Literal["sequential", "concurrent"]

# The four day types the real schedule uses. Kept as plain strings rather than a
# closed Literal because the day-type set lives in a workspace file and schools
# differ; these constants exist so callers stop retyping the ids.
DAY_TYPE_BOBCAT_HOUR = "bobcat_hour"
DAY_TYPE_FRIDAY = "friday"
DAY_TYPE_HOMEROOM_FIRST = "homeroom_first"
DAY_TYPE_PEP_RALLY = "pep_rally"

# Where a given moment falls. `no_school` covers weekends and any date the
# academic calendar reports as a non-instructional day.
Placement = Literal["before_school", "in_block", "passing", "after_school", "no_school"]


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


@dataclass(frozen=True)
class SubBlocks:
    """A container block's children, plus how they relate to the parent."""
    mode: SubBlockMode
    blocks: tuple["Block", ...]


@dataclass(frozen=True)
class Block:
    """One stretch of the bell schedule.

    `location` is populated only for concurrent children (a Bobcat Hour
    offering is "Robotics, Room 214"). Ordinary class blocks leave it empty.
    """
    block_id: str
    kind: BlockKind
    label: str
    start: time
    end: time
    sub_blocks: SubBlocks | None = None
    location: str = ""

    @property
    def duration_minutes(self) -> int:
        return _minutes(self.end) - _minutes(self.start)

    def contains(self, t: time) -> bool:
        """True when `t` is inside the block, start inclusive, end exclusive."""
        return self.start <= t < self.end

    def active_sub_block(self, t: time) -> "Block | None":
        """The sequential child covering `t`, if this block has one.

        Concurrent children are all active at once, so there is no single
        answer for them and this returns None. Ask `offerings` instead.
        """
        if self.sub_blocks is None or self.sub_blocks.mode != "sequential":
            return None
        for child in self.sub_blocks.blocks:
            if child.contains(t):
                return child
        return None

    @property
    def offerings(self) -> tuple["Block", ...]:
        """Concurrent children, or empty when this block has none."""
        if self.sub_blocks is None or self.sub_blocks.mode != "concurrent":
            return ()
        return self.sub_blocks.blocks


@dataclass(frozen=True)
class DayType:
    """An ordered list of blocks that makes up one kind of school day."""
    day_type_id: str
    label: str
    blocks: tuple[Block, ...]

    def find(self, block_id: str) -> Block | None:
        """The block with this id, searching sub-blocks too."""
        for block in self.walk():
            if block.block_id == block_id:
                return block
        return None

    def walk(self) -> Iterator[Block]:
        """Every block in the day, parents before their children."""
        for block in self.blocks:
            yield block
            if block.sub_blocks is not None:
                yield from block.sub_blocks.blocks

    def has_kind(self, kind: BlockKind) -> bool:
        """True when the day contains a block of this kind at any depth.

        Only bobcat_hour days carry a bobcat_hour block; the other three day
        types do not, and callers must not assume every day has one.
        """
        return any(block.kind == kind for block in self.walk())

    def first_of_kind(self, kind: BlockKind) -> Block | None:
        for block in self.walk():
            if block.kind == kind:
                return block
        return None

    @property
    def first_block(self) -> Block | None:
        return self.blocks[0] if self.blocks else None

    @property
    def last_block(self) -> Block | None:
        return self.blocks[-1] if self.blocks else None


@dataclass(frozen=True)
class BellSchedule:
    """Every day type a school runs, plus which one each date gets.

    `weekday_default` is keyed by `datetime.date.weekday()` (0 = Monday). A
    weekday absent from the mapping is not a school day. `date_overrides` is
    the calendar-authored exception list -- the "August 20th is Homeroom First"
    kind of fact -- and it wins over the weekday default.

    A same-day override ("the email at 6:50am says today is a Pep Rally") is
    deliberately not stored here. It is transient and lives in the resolver's
    call, because writing it here would mean editing the calendar file.
    """
    school: str
    timezone: str
    day_types: Mapping[str, DayType]
    weekday_default: Mapping[int, str] = field(default_factory=dict)
    date_overrides: Mapping[date, str] = field(default_factory=dict)
    is_sample: bool = False

    def day_type_id_for(self, day: date) -> str | None:
        """The scheduled day-type id for a date, ignoring the academic calendar.

        Returns None when the date is not a school day by the weekly pattern.
        No-school dates from the academic calendar are applied by the resolver,
        which owns that dependency; this stays pure.
        """
        override = self.date_overrides.get(day)
        if override is not None:
            return override
        return self.weekday_default.get(day.weekday())

    def day_type(self, day_type_id: str | None) -> DayType | None:
        if day_type_id is None:
            return None
        return self.day_types.get(day_type_id)


@dataclass(frozen=True)
class Resolved:
    """Where a single moment falls in the school day.

    `percent_complete` runs 0.0 to 1.0 across whichever span the moment sits
    in: the current block when `placement` is in_block, the gap between blocks
    when it is passing. It is 0.0 for every other placement.

    `sub_block` is the active sequential child of `block` -- the A-lunch half
    of 4th period -- and is None when the current block has no sequential
    children.
    """
    at: datetime
    placement: Placement
    day_type: DayType | None = None
    block: Block | None = None
    sub_block: Block | None = None
    next_block: Block | None = None
    elapsed_minutes: int = 0
    remaining_minutes: int = 0
    percent_complete: float = 0.0

    @property
    def is_school_day(self) -> bool:
        return self.placement != "no_school"

    @property
    def current_label(self) -> str:
        """What the top rail should call this moment."""
        if self.sub_block is not None:
            return self.sub_block.label
        if self.block is not None:
            return self.block.label
        if self.placement == "passing" and self.next_block is not None:
            return "Passing"
        if self.placement == "before_school":
            return "Before school"
        if self.placement == "after_school":
            return "After school"
        return "No school"


@dataclass(frozen=True)
class NextOccurrence:
    """The next time a given block kind runs, and on what date.

    Used by the Bobcat Hour panel, which always shows the next Bobcat Hour
    that has not ended yet and derives its own heading from `on`. On a Friday
    that resolves forward to Monday, which is why this returns a date rather
    than a bare block.
    """
    on: date
    day_type: DayType
    block: Block
    is_today: bool
