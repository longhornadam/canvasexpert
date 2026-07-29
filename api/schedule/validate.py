"""Structural checks over a loaded bell schedule.

A bell schedule with a quiet mistake in it puts the wrong times on a projector
for a whole day, and nobody notices until a class is late. So the checks here
are deliberately blunt and the messages name the offending block by id: a
teacher fixing a JSON file needs to know which line to look at, not that
something somewhere failed.

`validate` reports problems and never raises. Deciding what to do about them is
the loader's job.
"""
from __future__ import annotations

from datetime import time

from .models import BellSchedule, Block, DayType


def validate(schedule: BellSchedule) -> list[str]:
    """Every structural problem in the schedule, empty when it is clean."""
    problems: list[str] = []
    known = set(schedule.day_types)

    for weekday in sorted(schedule.weekday_default):
        day_type_id = schedule.weekday_default[weekday]
        if day_type_id not in known:
            problems.append(
                f"weekday_default[{weekday}] names day type "
                f"'{day_type_id}', which is not defined"
            )

    for day in sorted(schedule.date_overrides):
        day_type_id = schedule.date_overrides[day]
        if day_type_id not in known:
            problems.append(
                f"date_overrides[{day.isoformat()}] names day type "
                f"'{day_type_id}', which is not defined"
            )

    for day_type_id, day_type in schedule.day_types.items():
        problems.extend(_check_day_type(day_type_id, day_type))

    return problems


def _check_day_type(day_type_id: str, day_type: DayType) -> list[str]:
    problems: list[str] = []
    where = f"day type '{day_type_id}'"

    if day_type.day_type_id != day_type_id:
        problems.append(
            f"{where} carries the mismatched id '{day_type.day_type_id}'"
        )

    if not day_type.blocks:
        problems.append(f"{where} has no blocks")
        return problems

    problems.extend(_check_duplicate_ids(where, day_type))

    for block in day_type.walk():
        problems.extend(_check_span(where, block))

    problems.extend(_check_order(where, day_type.blocks))

    for block in day_type.blocks:
        problems.extend(_check_sub_blocks(where, block))

    return problems


def _check_duplicate_ids(where: str, day_type: DayType) -> list[str]:
    seen: set[str] = set()
    duplicated: list[str] = []
    for block in day_type.walk():
        if block.block_id in seen and block.block_id not in duplicated:
            duplicated.append(block.block_id)
        seen.add(block.block_id)
    return [
        f"{where} uses block id '{block_id}' more than once"
        for block_id in duplicated
    ]


def _check_span(where: str, block: Block) -> list[str]:
    if block.end > block.start:
        return []
    return [
        f"{where} block '{block.block_id}' ends at {_hm(block.end)}, "
        f"which is not after its start {_hm(block.start)}"
    ]


def _check_order(where: str, blocks: tuple[Block, ...]) -> list[str]:
    problems: list[str] = []
    for earlier, later in zip(blocks, blocks[1:]):
        if later.start < earlier.start:
            problems.append(
                f"{where} blocks are out of chronological order: "
                f"'{later.block_id}' starts at {_hm(later.start)}, before "
                f"'{earlier.block_id}' at {_hm(earlier.start)}"
            )
        elif later.start < earlier.end:
            problems.append(
                f"{where} blocks '{earlier.block_id}' and '{later.block_id}' "
                f"overlap: '{earlier.block_id}' runs to {_hm(earlier.end)} but "
                f"'{later.block_id}' starts at {_hm(later.start)}"
            )
    return problems


def _check_sub_blocks(where: str, parent: Block) -> list[str]:
    sub_blocks = parent.sub_blocks
    if sub_blocks is None:
        return []
    if sub_blocks.mode == "sequential":
        return _check_sequential(where, parent, sub_blocks.blocks)
    return _check_concurrent(where, parent, sub_blocks.blocks)


def _check_sequential(
    where: str, parent: Block, children: tuple[Block, ...]
) -> list[str]:
    """Sequential children must partition the parent end to end.

    A gap or an overlap here is the A/B lunch split disagreeing with the period
    that contains it, which would leave the rail with no answer for part of the
    period.
    """
    if not children:
        return [
            f"{where} block '{parent.block_id}' declares sequential "
            f"sub-blocks but lists none"
        ]

    problems: list[str] = []
    if children[0].start != parent.start:
        problems.append(
            f"{where} sub-block '{children[0].block_id}' starts at "
            f"{_hm(children[0].start)} but its parent "
            f"'{parent.block_id}' starts at {_hm(parent.start)}"
        )
    if children[-1].end != parent.end:
        problems.append(
            f"{where} sub-block '{children[-1].block_id}' ends at "
            f"{_hm(children[-1].end)} but its parent "
            f"'{parent.block_id}' ends at {_hm(parent.end)}"
        )
    for earlier, later in zip(children, children[1:]):
        if later.start > earlier.end:
            problems.append(
                f"{where} leaves a gap inside '{parent.block_id}' between "
                f"'{earlier.block_id}' ({_hm(earlier.end)}) and "
                f"'{later.block_id}' ({_hm(later.start)})"
            )
        elif later.start < earlier.end:
            problems.append(
                f"{where} sub-blocks '{earlier.block_id}' and "
                f"'{later.block_id}' overlap inside '{parent.block_id}'"
            )
    return problems


def _check_concurrent(
    where: str, parent: Block, children: tuple[Block, ...]
) -> list[str]:
    """Concurrent children all run for the parent's whole span.

    They are simultaneous offerings, so they partition nothing and they never
    carry a lunch split: the concurrent block is itself the lunch hour.
    """
    problems: list[str] = []
    for child in children:
        if child.start < parent.start or child.end > parent.end:
            problems.append(
                f"{where} offering '{child.block_id}' runs "
                f"{_hm(child.start)} to {_hm(child.end)}, outside its parent "
                f"'{parent.block_id}' ({_hm(parent.start)} to "
                f"{_hm(parent.end)})"
            )
        if child.kind == "lunch":
            problems.append(
                f"{where} offering '{child.block_id}' declares a lunch split "
                f"inside concurrent block '{parent.block_id}', which is "
                f"itself the lunch hour and has no A/B split"
            )
    return problems


def _hm(t: time) -> str:
    return t.strftime("%H:%M")
