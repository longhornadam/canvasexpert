"""The whole day, shaped for one screen.

Pure by design: no Jinja, no FastAPI, no disk, and no clock read. The instant
arrives as a parameter, which is what makes a frozen clock a caller's choice
rather than a special mode inside the page.

The return value is the render blob (build spec D1). It carries the entire
resolved day at once: every block with its times and its plan slice, the
resolved current moment, the next Bobcat Hour, events, banner text, and
anything worth telling the teacher. The browser then ticks its own clock
against that static structure and swaps the active block as time passes, so
nothing polls and no period boundary needs a second request.

Two rules worth stating once:

* **Budgets are imported, never retyped.** Every string bound for the screen
  passes through `clamp` at its field's budget from `api.glass.schema`, so the
  renderer truncates instead of reflowing a projected layout.
* **Nothing here raises for bad content.** A missing plan, a missing schedule,
  or a same-day override naming a day type the schedule does not define all
  come back as a calm note plus a working day. A blank projector is a worse
  failure than a note.
"""
from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from datetime import time as time_type
from datetime import timedelta
from typing import Any, Sequence

from api.glass.schema import (
    BUDGET_LEARNING_GOAL,
    BUDGET_OFFERING_LABEL,
    BUDGET_OFFERING_LOCATION,
    BUDGET_SUCCESS_CRITERION,
    BUDGET_WORK_DETAIL,
    BUDGET_WORK_NAME,
    DayPlan,
    SectionPlan,
    clamp,
)
from api.schedule.models import BellSchedule, Block, NextOccurrence, Resolved
from api.schedule.resolver import next_occurrence, resolve

# The block kind whose contents get their own pane. Only bobcat_hour days carry
# one, which is why the pane resolves forward rather than assuming today.
BOBCAT_HOUR_KIND = "bobcat_hour"

# How far ahead to look for the next one. Two weeks covers a long weekend, a
# holiday, and a week of Pep Rally days without pretending to know a month out.
BOBCAT_SEARCH_DAYS = 14

# Written out rather than taken from strftime so the heading reads the same on
# every machine regardless of locale.
WEEKDAY_NAMES = (
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
)

# The one thing the Bobcat Hour pane says when the schedule never gets there.
NO_BOBCAT_HOUR_NOTE = "No Bobcat Hour in the next two weeks of the schedule."

# What the pane says when the next one is not today, so today's offerings would
# be the wrong list to show.
OFFERINGS_PENDING_NOTE = "Offerings post with that day's plan."


def build_view(
    *,
    schedule: BellSchedule | None,
    plan: DayPlan | None,
    at: datetime,
    no_school_dates: frozenset[date_type] = frozenset(),
    notes: Sequence[str] = (),
    next_plan: DayPlan | None = None,
    clock_frozen: bool = False,
) -> dict[str, Any]:
    """Everything the page needs for the whole day, in one structure.

    `notes` are whatever the loaders already worked out, such as the sample-data
    note and the missing-plan note. They are carried through and joined by
    anything this function discovers itself.

    `next_plan` is the day plan for the next Bobcat Hour that falls on a date
    after today. It supplies the pane once today's block has ended, which is how
    the pane flips from today to tomorrow with no second request. Without it the
    pane still shows its heading and its times and says that the offerings
    arrive with that day's plan, because showing today's list under tomorrow's
    heading would be worse than showing nothing.
    """
    collected: list[str] = [str(note) for note in notes if note]

    override = _usable_override(schedule, plan, collected)
    resolved = _resolve(schedule, at, no_school_dates, override, collected)
    occurrence = _next_bobcat(schedule, at, no_school_dates, override, collected)
    after = _bobcat_after_today(schedule, at, no_school_dates, collected)

    day_type = resolved.day_type
    blocks = tuple(day_type.blocks) if day_type is not None else ()
    section_of = plan.section if plan is not None else (lambda block_id: None)

    return {
        "school": schedule.school if schedule is not None else "",
        "timezone": schedule.timezone if schedule is not None else "",
        "date": at.date().isoformat(),
        "weekday": WEEKDAY_NAMES[at.date().weekday()],
        "at": at.isoformat(timespec="seconds"),
        "at_seconds": _seconds_of_day(at.time()),
        "clock": _time_text(at.time()),
        "clock_frozen": bool(clock_frozen),
        "is_sample": bool(schedule is not None and schedule.is_sample),
        "has_schedule": schedule is not None,
        "has_plan": plan is not None,
        "is_school_day": resolved.is_school_day and bool(blocks),
        "day_type": _day_type_blob(resolved),
        "blocks": [_block_blob(block, section_of) for block in blocks],
        "current": _current_blob(resolved, section_of),
        "bobcat_hour": _bobcat_blob(occurrence, at.date(), plan, next_plan),
        # The pane the browser swaps in once today's block has ended. Absent
        # unless the pane is currently showing a Bobcat Hour that is today,
        # since a pane already looking forward has nothing to flip to.
        "bobcat_hour_after": (
            _bobcat_blob(after, at.date(), plan, next_plan)
            if occurrence is not None
            and occurrence.on == at.date()
            and after is not None
            else {}
        ),
        "events": _events_blob(plan),
        "banner": _banner_blob(resolved, section_of),
        "rail_notes": _rail_notes(schedule, plan),
        "notes": collected,
    }


def bobcat_heading(occurrence: NextOccurrence | None, today: date_type) -> str:
    """One rule over the next occurrence, not a morning mode and an afternoon one.

    Today reads "Today during Bobcat Hour" and tomorrow reads "Tomorrow during
    Bobcat Hour". Anything further out is named by its weekday, so a Friday
    reads "Monday during Bobcat Hour" without anything being switched. Two
    hardcoded states would leave the pane empty every Friday, which is the whole
    reason this is derived.
    """
    if occurrence is None:
        return ""
    days_ahead = (occurrence.on - today).days
    if days_ahead <= 0:
        return "Today during Bobcat Hour"
    if days_ahead == 1:
        return "Tomorrow during Bobcat Hour"
    return f"{WEEKDAY_NAMES[occurrence.on.weekday()]} during Bobcat Hour"


# ------------------------------------------------------------------ resolution


def _usable_override(
    schedule: BellSchedule | None, plan: DayPlan | None, collected: list[str]
) -> str | None:
    """The plan's same-day override, dropped with a note when unusable.

    The resolver refuses an override it cannot honour, and rightly so. Here that
    refusal becomes a note and a normal day, because the screen has to keep
    working while the teacher fixes the file.
    """
    wanted = plan.day_type_override if plan is not None else None
    if not wanted:
        return None
    if schedule is None:
        return None
    if wanted not in schedule.day_types:
        collected.append(
            f"Today's plan asks for a '{wanted}' day, which this bell schedule "
            f"does not define, so the usual day is showing."
        )
        return None
    return wanted


def _resolve(
    schedule: BellSchedule | None,
    at: datetime,
    no_school_dates: frozenset[date_type],
    override: str | None,
    collected: list[str],
) -> Resolved:
    if schedule is None:
        return Resolved(at=at, placement="no_school")
    try:
        return resolve(
            schedule, at, no_school_dates=no_school_dates, override=override
        )
    except ValueError as err:
        collected.append(str(err))
        return resolve(schedule, at, no_school_dates=no_school_dates)


def _next_bobcat(
    schedule: BellSchedule | None,
    at: datetime,
    no_school_dates: frozenset[date_type],
    override: str | None,
    collected: list[str],
) -> NextOccurrence | None:
    if schedule is None:
        return None
    try:
        return next_occurrence(
            schedule,
            at,
            BOBCAT_HOUR_KIND,
            no_school_dates=no_school_dates,
            override=override,
            search_days=BOBCAT_SEARCH_DAYS,
        )
    except ValueError as err:
        collected.append(str(err))
        return None


def _bobcat_after_today(
    schedule: BellSchedule | None,
    at: datetime,
    no_school_dates: frozenset[date_type],
    collected: list[str],
) -> NextOccurrence | None:
    """The first Bobcat Hour on a date after today.

    Searched from tomorrow's midnight so today can never answer. A same-day
    override says nothing about tomorrow, so none is passed.
    """
    if schedule is None:
        return None
    tomorrow = datetime.combine(at.date(), time_type.min) + timedelta(days=1)
    try:
        return next_occurrence(
            schedule,
            tomorrow,
            BOBCAT_HOUR_KIND,
            no_school_dates=no_school_dates,
            search_days=BOBCAT_SEARCH_DAYS,
        )
    except ValueError as err:
        collected.append(str(err))
        return None


# ----------------------------------------------------------------------- parts


def _day_type_blob(resolved: Resolved) -> dict[str, str]:
    day_type = resolved.day_type
    if day_type is None:
        return {"id": "", "label": "No school"}
    return {"id": day_type.day_type_id, "label": day_type.label}


def _block_blob(block: Block, section_of) -> dict[str, Any]:
    blob = _bare_block_blob(block, section_of)
    if block.sub_blocks is not None:
        blob["sub_blocks"] = {
            "mode": block.sub_blocks.mode,
            "blocks": [
                _bare_block_blob(child, section_of)
                for child in block.sub_blocks.blocks
            ],
        }
    else:
        blob["sub_blocks"] = {"mode": "", "blocks": []}
    return blob


def _bare_block_blob(block: Block, section_of) -> dict[str, Any]:
    return {
        "id": block.block_id,
        "kind": block.kind,
        "label": block.label,
        "location": block.location,
        "start": block.start.isoformat(timespec="minutes"),
        "end": block.end.isoformat(timespec="minutes"),
        "start_text": _time_text(block.start),
        "end_text": _time_text(block.end),
        "start_seconds": _seconds_of_day(block.start),
        "end_seconds": _seconds_of_day(block.end),
        "duration_minutes": block.duration_minutes,
        "plan": _plan_blob(section_of(block.block_id)),
    }


def _plan_blob(section: SectionPlan | None) -> dict[str, Any]:
    """One block's slice, every field already cut to its budget."""
    if section is None:
        return {"learning_goal": "", "success_criteria": [], "work": [], "banner": []}
    return {
        "learning_goal": clamp(section.learning_goal, BUDGET_LEARNING_GOAL),
        "success_criteria": [
            clamp(criterion, BUDGET_SUCCESS_CRITERION)
            for criterion in section.success_criteria
        ],
        "work": [
            {
                "name": clamp(item.name, BUDGET_WORK_NAME),
                "detail": clamp(item.detail, BUDGET_WORK_DETAIL),
            }
            for item in section.work
        ],
        "banner": list(section.banner),
    }


def _current_blob(resolved: Resolved, section_of) -> dict[str, Any]:
    block = resolved.block
    sub_block = resolved.sub_block
    next_block = resolved.next_block
    section = section_of(block.block_id) if block is not None else None
    remaining_seconds = _remaining_seconds(resolved)
    return {
        "placement": resolved.placement,
        "label": resolved.current_label,
        "block_id": block.block_id if block is not None else "",
        "sub_block_id": sub_block.block_id if sub_block is not None else "",
        "elapsed_minutes": resolved.elapsed_minutes,
        "remaining_minutes": resolved.remaining_minutes,
        "remaining_seconds": remaining_seconds,
        "remaining_text": _remaining_text(resolved),
        "countdown": _countdown_text(remaining_seconds),
        "percent": round(resolved.percent_complete * 100),
        "next_block_id": next_block.block_id if next_block is not None else "",
        "next_label": next_block.label if next_block is not None else "",
        "plan": _plan_blob(section),
    }


def _remaining_seconds(resolved: Resolved) -> int:
    """Seconds to the next bell, at the resolution a countdown needs.

    The resolver reports whole minutes because that is what a rail should say
    all day. A passing-period countdown wants the seconds too, and it is the
    same span measured twice rather than a second opinion about which span.
    """
    at_seconds = _seconds_of_day(resolved.at.time())
    if resolved.placement == "in_block":
        span = resolved.sub_block if resolved.sub_block is not None else resolved.block
        if span is not None:
            return max(_seconds_of_day(span.end) - at_seconds, 0)
    if resolved.placement in ("passing", "before_school"):
        if resolved.next_block is not None:
            return max(_seconds_of_day(resolved.next_block.start) - at_seconds, 0)
    return 0


def _countdown_text(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


def _bobcat_blob(
    occurrence: NextOccurrence | None,
    today: date_type,
    plan: DayPlan | None,
    next_plan: DayPlan | None,
) -> dict[str, Any]:
    """The pane's whole contents, heading included.

    Offerings only ever come from the plan for the date being shown. When that
    date is not today and its plan is not written yet, the pane says so rather
    than putting today's clubs under tomorrow's heading.
    """
    if occurrence is None:
        return {
            "heading": "Bobcat Hour",
            "available": False,
            "note": NO_BOBCAT_HOUR_NOTE,
            "on": "",
            "is_today": False,
            "label": "",
            "start_text": "",
            "end_text": "",
            "end_seconds": 0,
            "offerings": [],
            "here": {},
        }

    # Compared against the date rather than read off the occurrence: the
    # follow-up lookup is anchored at tomorrow, so its own `is_today` flag means
    # "the first day I searched" and would put today's offerings under
    # tomorrow's heading.
    is_today = occurrence.on == today
    source = plan if is_today else next_plan
    offerings = (
        [
            {
                "label": clamp(offering.label, BUDGET_OFFERING_LABEL),
                "location": clamp(offering.location, BUDGET_OFFERING_LOCATION),
            }
            for offering in source.school_wide.bobcat_hour_offerings
        ]
        if source is not None
        else []
    )
    here = source.teacher_bobcat_hour if source is not None else None
    return {
        "heading": bobcat_heading(occurrence, today),
        "available": True,
        "note": "" if source is not None else OFFERINGS_PENDING_NOTE,
        "on": occurrence.on.isoformat(),
        "is_today": is_today,
        "label": occurrence.block.label,
        "start_text": _time_text(occurrence.block.start),
        "end_text": _time_text(occurrence.block.end),
        "end_seconds": _seconds_of_day(occurrence.block.end),
        "offerings": offerings,
        "here": (
            {
                "label": clamp(here.label, BUDGET_OFFERING_LABEL),
                "location": clamp(here.location, BUDGET_OFFERING_LOCATION),
            }
            if here is not None
            else {}
        ),
    }


def _events_blob(plan: DayPlan | None) -> list[dict[str, str]]:
    """School-wide reminders, in plan order.

    No budget is defined for these, so they are carried whole and the pane sheds
    whole items when the rail runs short of room.
    """
    if plan is None:
        return []
    return [
        {"label": event.label, "when": event.when}
        for event in plan.school_wide.events
    ]


def _banner_blob(resolved: Resolved, section_of) -> list[str]:
    """Rotating text for the current block, written by hand in the plan.

    Nothing here reads the mirror or the vault. The banner is plan text and
    only plan text this batch.
    """
    block = resolved.block
    if block is None:
        return []
    section = section_of(block.block_id)
    return list(section.banner) if section is not None else []


def _rail_notes(schedule: BellSchedule | None, plan: DayPlan | None) -> list[str]:
    """Short quiet tags for the top rail, distinct from the full notes list.

    The loaders explain a problem in a sentence, which is right for a teacher
    reading a page and wrong for a projected rail, so the rail gets a few words
    and the sentence stays in `notes`.
    """
    out: list[str] = []
    if schedule is None:
        out.append("No bell schedule yet")
    elif schedule.is_sample:
        out.append("Sample schedule")
    if plan is None:
        out.append("No plan for today")
    return out


# ------------------------------------------------------------------ formatting


def _seconds_of_day(value: time_type) -> int:
    return value.hour * 3600 + value.minute * 60 + value.second


def _time_text(value: time_type) -> str:
    """A wall-clock reading with no leading zero and no meridiem.

    A room knows whether it is morning, and "1:05" is read faster from the back
    row than "13:05" or "1:05 PM".
    """
    hour = value.hour % 12 or 12
    return f"{hour}:{value.minute:02d}"


def _remaining_text(resolved: Resolved) -> str:
    """What the rail says about time left, in the words the placement earns."""
    minutes = resolved.remaining_minutes
    next_label = resolved.next_block.label if resolved.next_block is not None else ""
    if resolved.placement == "in_block":
        return f"{minutes} min left" if minutes else "ending now"
    if resolved.placement == "passing":
        return f"{minutes} min to {next_label}" if next_label else f"{minutes} min"
    if resolved.placement == "before_school":
        return f"{minutes} min to first bell"
    return ""
