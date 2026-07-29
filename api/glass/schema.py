"""What a day plan is, and how much of it fits on the screen.

The character budgets are the interesting part. They are a property of the
schema rather than of the renderer, because the screen is read from the back
of a classroom and a goal that wraps to three lines pushes everything else off
the bottom. So the budgets live here once, the validator reports over-budget
text at compose time so the teacher can shorten it themselves, and the
renderer clamps whatever still arrives too long. Two copies of these numbers
would drift, so there is one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_type
from typing import Any, Mapping

DAY_PLAN_FORMAT = "canvasexpert.day_plan/1"

# How much of each field fits at the real projector size. Named constants
# below read from this mapping so there is a single source for each number.
CHARACTER_BUDGETS: Mapping[str, int] = {
    "learning_goal": 90,
    "success_criterion": 40,
    "work_name": 34,
    "work_detail": 44,
    "offering_label": 30,
    "offering_location": 12,
}

BUDGET_LEARNING_GOAL = CHARACTER_BUDGETS["learning_goal"]
BUDGET_SUCCESS_CRITERION = CHARACTER_BUDGETS["success_criterion"]
BUDGET_WORK_NAME = CHARACTER_BUDGETS["work_name"]
BUDGET_WORK_DETAIL = CHARACTER_BUDGETS["work_detail"]
BUDGET_OFFERING_LABEL = CHARACTER_BUDGETS["offering_label"]
BUDGET_OFFERING_LOCATION = CHARACTER_BUDGETS["offering_location"]

# One character, so a clamped string still fits its budget exactly.
ELLIPSIS = "…"


class DayPlanError(ValueError):
    """A day plan file cannot be read. The message names what to fix."""


@dataclass(frozen=True)
class WorkItem:
    """One thing the class is working on today."""
    name: str
    detail: str = ""


@dataclass(frozen=True)
class Offering:
    """Something on offer during the lunch-and-tutorials block."""
    label: str
    location: str = ""


@dataclass(frozen=True)
class TeacherBobcatHour:
    """What is happening in this teacher's own room during that block."""
    label: str
    location: str = ""


@dataclass(frozen=True)
class Event:
    """A short school-wide reminder. `when` is whatever reads well."""
    label: str
    when: str = ""


@dataclass(frozen=True)
class SchoolWide:
    """The part of the day that is the same for every class."""
    events: tuple[Event, ...] = ()
    bobcat_hour_offerings: tuple[Offering, ...] = ()


@dataclass(frozen=True)
class SectionPlan:
    """One block's slice of the day, keyed by block id rather than by section.

    The resolver already knows which block is in the room, so keying by block
    id means rendering needs no lookup and no Canvas section involvement.
    """
    block_id: str
    learning_goal: str = ""
    success_criteria: tuple[str, ...] = ()
    work: tuple[WorkItem, ...] = ()
    banner: tuple[str, ...] = ()


@dataclass(frozen=True)
class DayPlan:
    """One teaching day, composed once in the morning.

    `day_type_override` is the same-day override: a day type id that wins over
    the calendar for this date only. It lives on the plan because the plan is
    the thing being written at 6:55am after the email arrives, and editing the
    schedule file instead would leave the wrong day type there tomorrow.
    """
    date: date_type
    day_type_override: str | None = None
    school_wide: SchoolWide = SchoolWide()
    teacher_bobcat_hour: TeacherBobcatHour | None = None
    sections: Mapping[str, SectionPlan] = field(default_factory=dict)
    is_sample: bool = False

    def section(self, block_id: str | None) -> SectionPlan | None:
        """This block's slice, or None when the plan does not cover it.

        A block with no entry is normal, not a mistake: a conference period or
        a duty period simply has nothing to show.
        """
        if not block_id:
            return None
        return self.sections.get(block_id)


def clamp(text: str, budget: int) -> str:
    """Shorten `text` to fit `budget`, ending in a single ellipsis character.

    The renderer's half of the budget rule. Never returns more characters than
    the budget, because the layout has no room to give.
    """
    value = "" if text is None else str(text)
    if budget <= 0:
        return ""
    if len(value) <= budget:
        return value
    if budget == 1:
        return ELLIPSIS
    return value[: budget - 1].rstrip() + ELLIPSIS


# ---------------------------------------------------------------- pure parsing


def _is_comment_key(key: Any) -> bool:
    """True for the `_comment` and `_example` keys the shipped files carry."""
    return isinstance(key, str) and key.startswith("_")


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _string_list(raw: Any, *, where: str, field_name: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise DayPlanError(f"{where} needs {field_name} written as a list")
    return tuple(_text(item) for item in raw if _text(item))


def _parse_work(raw: Any, *, where: str) -> tuple[WorkItem, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise DayPlanError(f"{where} needs work written as a list")
    items: list[WorkItem] = []
    for index, entry in enumerate(raw, start=1):
        if isinstance(entry, dict) and entry and all(map(_is_comment_key, entry)):
            continue
        if not isinstance(entry, dict):
            raise DayPlanError(
                f"{where} work item {index} should have a name and a detail"
            )
        name = _text(entry.get("name"))
        if not name:
            raise DayPlanError(f"{where} work item {index} has no name")
        items.append(WorkItem(name=name, detail=_text(entry.get("detail"))))
    return tuple(items)


def _parse_section(block_id: str, raw: Any, *, on: str) -> SectionPlan:
    where = f"the day plan for {on} block '{block_id}'"
    if not isinstance(raw, dict):
        raise DayPlanError(f"{where} is not a set of fields")
    return SectionPlan(
        block_id=block_id,
        learning_goal=_text(raw.get("learning_goal")),
        success_criteria=_string_list(
            raw.get("success_criteria"), where=where, field_name="success_criteria"
        ),
        work=_parse_work(raw.get("work"), where=where),
        banner=_string_list(raw.get("banner"), where=where, field_name="banner"),
    )


def _parse_school_wide(raw: Any, *, on: str) -> SchoolWide:
    if raw is None:
        return SchoolWide()
    where = f"the day plan for {on}"
    if not isinstance(raw, dict):
        raise DayPlanError(f"{where} needs school_wide written as a set of fields")

    raw_events = raw.get("events") or []
    if not isinstance(raw_events, list):
        raise DayPlanError(f"{where} needs school_wide events written as a list")
    events: list[Event] = []
    for index, entry in enumerate(raw_events, start=1):
        if not isinstance(entry, dict):
            raise DayPlanError(f"{where} event {index} should have a label")
        label = _text(entry.get("label"))
        if not label:
            raise DayPlanError(f"{where} event {index} has no label")
        events.append(Event(label=label, when=_text(entry.get("when"))))

    raw_offerings = raw.get("bobcat_hour_offerings") or []
    if not isinstance(raw_offerings, list):
        raise DayPlanError(
            f"{where} needs school_wide bobcat_hour_offerings written as a list"
        )
    offerings: list[Offering] = []
    for index, entry in enumerate(raw_offerings, start=1):
        if not isinstance(entry, dict):
            raise DayPlanError(
                f"{where} Bobcat Hour offering {index} should have a label and a location"
            )
        label = _text(entry.get("label"))
        if not label:
            raise DayPlanError(f"{where} Bobcat Hour offering {index} has no label")
        offerings.append(Offering(label=label, location=_text(entry.get("location"))))

    return SchoolWide(events=tuple(events), bobcat_hour_offerings=tuple(offerings))


def _parse_teacher(raw: Any, *, on: str) -> TeacherBobcatHour | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise DayPlanError(
            f"the day plan for {on} needs teacher written as a set of fields"
        )
    entry = raw.get("bobcat_hour_here")
    if not isinstance(entry, dict):
        return None
    label = _text(entry.get("label"))
    if not label:
        # An empty label is how the blank template ships, and it is also the
        # honest answer on a day with nothing happening in this room.
        return None
    return TeacherBobcatHour(label=label, location=_text(entry.get("location")))


def parse_day_plan(data: Mapping[str, Any]) -> DayPlan:
    """Turn one day plan file's contents into a `DayPlan`.

    Pure: no disk, no clock. Failures raise `DayPlanError` naming the block and
    the field, because the person fixing the file is a teacher between classes.
    """
    if not isinstance(data, Mapping):
        raise DayPlanError("a day plan file should hold a set of fields")

    file_format = _text(data.get("format"))
    if file_format != DAY_PLAN_FORMAT:
        shown = file_format or "nothing"
        raise DayPlanError(
            f"this file says its format is {shown}, and a day plan needs "
            f"'{DAY_PLAN_FORMAT}'."
        )

    raw_date = _text(data.get("date"))
    if not raw_date:
        raise DayPlanError(
            "the day plan has no date. Add one in YYYY-MM-DD form, matching the "
            "file name."
        )
    try:
        on = date_type.fromisoformat(raw_date)
    except ValueError:
        raise DayPlanError(
            f"the day plan has a date of '{raw_date}'. Dates are written "
            f"YYYY-MM-DD, for example 2099-09-14."
        ) from None

    raw_sections = data.get("sections") or {}
    if not isinstance(raw_sections, dict):
        raise DayPlanError(
            f"the day plan for {raw_date} should pair a block id with that "
            f"block's plan"
        )
    sections = {
        _text(key): _parse_section(_text(key), value, on=raw_date)
        for key, value in raw_sections.items()
        if not _is_comment_key(key)
    }

    return DayPlan(
        date=on,
        day_type_override=_text(data.get("day_type_override")) or None,
        school_wide=_parse_school_wide(data.get("school_wide"), on=raw_date),
        teacher_bobcat_hour=_parse_teacher(data.get("teacher"), on=raw_date),
        sections=sections,
        is_sample=bool(data.get("sample")),
    )


# ------------------------------------------------------------------- validation


def _over(label: str, text: str, budget: int) -> str | None:
    if len(text) <= budget:
        return None
    return f"{label} is {len(text)} characters and {budget} fit on the screen"


def validate_day_plan(plan: DayPlan) -> list[str]:
    """Every field that will not fit, named, with its length and its budget.

    This is the compose-time gate: a teacher shortening their own goal reads
    better than the renderer cutting it off. The renderer clamps anything that
    still arrives long, so nothing here blocks the screen from working.
    """
    problems: list[str] = []

    for index, offering in enumerate(plan.school_wide.bobcat_hour_offerings, start=1):
        problems.append(
            _over(
                f"Bobcat Hour offering {index} label ('{offering.label}')",
                offering.label,
                BUDGET_OFFERING_LABEL,
            )
        )
        problems.append(
            _over(
                f"Bobcat Hour offering {index} location ('{offering.location}')",
                offering.location,
                BUDGET_OFFERING_LOCATION,
            )
        )

    here = plan.teacher_bobcat_hour
    if here is not None:
        problems.append(
            _over("your own Bobcat Hour label", here.label, BUDGET_OFFERING_LABEL)
        )
        problems.append(
            _over("your own Bobcat Hour location", here.location, BUDGET_OFFERING_LOCATION)
        )

    for block_id in sorted(plan.sections):
        section = plan.sections[block_id]
        where = f"block '{block_id}'"
        problems.append(
            _over(f"{where} learning goal", section.learning_goal, BUDGET_LEARNING_GOAL)
        )
        for index, criterion in enumerate(section.success_criteria, start=1):
            problems.append(
                _over(
                    f"{where} success criterion {index}",
                    criterion,
                    BUDGET_SUCCESS_CRITERION,
                )
            )
        for index, item in enumerate(section.work, start=1):
            problems.append(
                _over(f"{where} work item {index} name", item.name, BUDGET_WORK_NAME)
            )
            problems.append(
                _over(f"{where} work item {index} detail", item.detail, BUDGET_WORK_DETAIL)
            )

    return [problem for problem in problems if problem]
