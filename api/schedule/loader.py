"""Read a bell schedule off disk and turn it into models.

Two halves, kept apart on purpose. `parse_bell_schedule` is pure dict to
model, so every error it raises can name the day type and block a teacher
should go look at. Discovery is the impure half: it asks the workspace owner
where the folder is and decides which of the files in it to trust.

The sample rule is the reason discovery is more than a glob. `Library/Calendars`
globs every CSV it finds, which is fine for a calendar and wrong for a bell
schedule: a shipped fictional sample would put the wrong times on a projector
all day. So every shipped file carries `"sample": true`, a real file omits it,
and this module prefers the real one. Two real files is reported rather than
guessed at.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, time
from typing import Any, Mapping

from api.schedule.models import (
    SCHEDULE_FORMAT,
    BellSchedule,
    Block,
    DayType,
    SubBlocks,
)

BELL_SCHEDULE_FOLDER = "Glass"
SECTION_MAP_FORMAT = "canvasexpert.section_map/1"
SECTION_MAP_FILENAME = "section-map.json"

_SUB_BLOCK_MODES = ("sequential", "concurrent")


class BellScheduleError(ValueError):
    """A bell schedule file cannot be read. The message names what to fix."""


@dataclass(frozen=True)
class SectionRef:
    """The Canvas section that meets in one block."""
    course_id: str = ""
    section_name: str = ""


@dataclass(frozen=True)
class SectionMap:
    """Which Canvas section meets in which block, keyed by block id.

    Parsed and validated here so the file is known good, but read by nobody
    yet: it exists so a later batch can answer "4th period is Canvas section
    X" without the schedule and the roster becoming coupled today.
    """
    sections: Mapping[str, SectionRef]
    is_sample: bool = False


# ---------------------------------------------------------------- pure parsing


def _is_comment_key(key: Any) -> bool:
    """True for the `_comment` and `_example` keys the shipped files carry.

    The templates explain themselves inline, which is worth more to a teacher
    than a tidy parser, so anything underscored is documentation and skipped.
    """
    return isinstance(key, str) and key.startswith("_")


def _is_comment_entry(value: Any) -> bool:
    """True for a list entry that is nothing but inline documentation."""
    return isinstance(value, dict) and bool(value) and all(map(_is_comment_key, value))


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _parse_time(raw: Any, *, where: str, field_name: str) -> time:
    text = _text(raw)
    if not text:
        raise BellScheduleError(f"{where} has no {field_name}")
    try:
        return time.fromisoformat(text)
    except ValueError:
        raise BellScheduleError(
            f"{where} has a {field_name} of '{text}', which is not an HH:MM "
            f"24-hour time. Afternoon times count on past 12, so 1:05pm is 13:05."
        ) from None


def _parse_block(raw: Any, *, day_type_id: str, depth: int = 0) -> Block:
    if not isinstance(raw, dict):
        raise BellScheduleError(
            f"day type '{day_type_id}' has a block that is not a set of fields"
        )
    block_id = _text(raw.get("id"))
    if not block_id:
        raise BellScheduleError(
            f"day type '{day_type_id}' has a block with no id. Give it a short "
            f"one such as 'p1'."
        )
    where = f"day type '{day_type_id}' block '{block_id}'"
    start = _parse_time(raw.get("start"), where=where, field_name="start time")
    end = _parse_time(raw.get("end"), where=where, field_name="end time")

    sub_blocks = None
    raw_sub = raw.get("sub_blocks")
    if raw_sub is not None:
        if depth:
            raise BellScheduleError(
                f"{where} is already inside another block, so it cannot have "
                f"sub-blocks of its own."
            )
        sub_blocks = _parse_sub_blocks(raw_sub, day_type_id=day_type_id, where=where)

    return Block(
        block_id=block_id,
        kind=_text(raw.get("kind")) or "class",
        label=_text(raw.get("label")) or block_id,
        start=start,
        end=end,
        sub_blocks=sub_blocks,
        location=_text(raw.get("location")),
    )


def _parse_sub_blocks(raw: Any, *, day_type_id: str, where: str) -> SubBlocks:
    if not isinstance(raw, dict):
        raise BellScheduleError(f"{where} has sub_blocks that are not a set of fields")
    mode = _text(raw.get("mode"))
    if mode not in _SUB_BLOCK_MODES:
        raise BellScheduleError(
            f"{where} has a sub_blocks mode of '{mode}'. Use 'sequential' for a "
            f"period split into A and B lunch, or 'concurrent' for several "
            f"things running at once."
        )
    raw_blocks = raw.get("blocks") or []
    if not isinstance(raw_blocks, list):
        raise BellScheduleError(f"{where} has a sub_blocks list that is not a list")
    children = tuple(
        _parse_block(child, day_type_id=day_type_id, depth=1)
        for child in raw_blocks
        if not _is_comment_entry(child)
    )
    return SubBlocks(mode=mode, blocks=children)


def _parse_day_type(day_type_id: str, raw: Any) -> DayType:
    if not isinstance(raw, dict):
        raise BellScheduleError(f"day type '{day_type_id}' is not a set of fields")
    raw_blocks = raw.get("blocks") or []
    if not isinstance(raw_blocks, list):
        raise BellScheduleError(
            f"day type '{day_type_id}' needs a list of blocks in the order they run"
        )
    blocks = tuple(
        _parse_block(block, day_type_id=day_type_id)
        for block in raw_blocks
        if not _is_comment_entry(block)
    )
    return DayType(
        day_type_id=day_type_id,
        label=_text(raw.get("label")) or day_type_id,
        blocks=blocks,
    )


def _parse_weekday_default(raw: Any) -> dict[int, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise BellScheduleError(
            "weekday_default should pair a weekday number with a day type id"
        )
    out: dict[int, str] = {}
    for key, value in raw.items():
        if _is_comment_key(key):
            continue
        try:
            weekday = int(str(key).strip())
        except ValueError:
            raise BellScheduleError(
                f"weekday_default has a key of '{key}'. Keys are weekday numbers "
                f"written as text, \"0\" for Monday through \"6\" for Sunday."
            ) from None
        if not 0 <= weekday <= 6:
            raise BellScheduleError(
                f"weekday_default has a key of '{key}'. Weekdays run from 0 "
                f"(Monday) to 6 (Sunday)."
            )
        day_type_id = _text(value)
        if not day_type_id:
            raise BellScheduleError(
                f"weekday_default key '{key}' has no day type id. Leave the "
                f"weekday out entirely when it is not a school day."
            )
        out[weekday] = day_type_id
    return out


def _parse_date_overrides(raw: Any) -> dict[date, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise BellScheduleError(
            "date_overrides should pair a date with a day type id"
        )
    out: dict[date, str] = {}
    for key, value in raw.items():
        if _is_comment_key(key):
            continue
        text = _text(key)
        try:
            day = date.fromisoformat(text)
        except ValueError:
            raise BellScheduleError(
                f"date_overrides has a date of '{text}'. Dates are written "
                f"YYYY-MM-DD, for example 2099-09-08."
            ) from None
        day_type_id = _text(value)
        if not day_type_id:
            raise BellScheduleError(
                f"date_overrides for {text} has no day type id"
            )
        out[day] = day_type_id
    return out


def parse_bell_schedule(data: Mapping[str, Any]) -> BellSchedule:
    """Turn one bell schedule file's contents into a `BellSchedule`.

    Pure: no disk, no clock. Every failure raises `BellScheduleError` with a
    message that names the day type and block to go look at, because the
    person who has to fix the file is a teacher looking at a projector.
    """
    if not isinstance(data, Mapping):
        raise BellScheduleError("a bell schedule file should hold a set of fields")

    file_format = _text(data.get("format"))
    if file_format != SCHEDULE_FORMAT:
        shown = file_format or "nothing"
        raise BellScheduleError(
            f"this file says its format is {shown}, and a bell schedule needs "
            f"'{SCHEDULE_FORMAT}'."
        )

    raw_day_types = data.get("day_types") or {}
    if not isinstance(raw_day_types, dict):
        raise BellScheduleError(
            "day_types should pair a day type id with that day's blocks"
        )
    day_types = {
        str(key): _parse_day_type(str(key), value)
        for key, value in raw_day_types.items()
        if not _is_comment_key(key)
    }

    return BellSchedule(
        school=_text(data.get("school")),
        timezone=_text(data.get("timezone")),
        day_types=day_types,
        weekday_default=_parse_weekday_default(data.get("weekday_default")),
        date_overrides=_parse_date_overrides(data.get("date_overrides")),
        is_sample=bool(data.get("sample")),
    )


def parse_section_map(data: Mapping[str, Any]) -> SectionMap:
    """Turn a section-map file's contents into a `SectionMap`."""
    if not isinstance(data, Mapping):
        raise BellScheduleError("a section map file should hold a set of fields")

    file_format = _text(data.get("format"))
    if file_format != SECTION_MAP_FORMAT:
        shown = file_format or "nothing"
        raise BellScheduleError(
            f"this file says its format is {shown}, and a section map needs "
            f"'{SECTION_MAP_FORMAT}'."
        )

    raw_sections = data.get("sections") or {}
    if not isinstance(raw_sections, dict):
        raise BellScheduleError(
            "sections should pair a block id with the Canvas section that meets in it"
        )
    sections: dict[str, SectionRef] = {}
    for key, value in raw_sections.items():
        if _is_comment_key(key):
            continue
        block_id = _text(key)
        if not isinstance(value, dict):
            raise BellScheduleError(
                f"section map entry '{block_id}' should have a course_id and a "
                f"section_name"
            )
        sections[block_id] = SectionRef(
            course_id=_text(value.get("course_id")),
            section_name=_text(value.get("section_name")),
        )
    return SectionMap(sections=sections, is_sample=bool(data.get("sample")))


# ------------------------------------------------------------------ disk reads


def _read_json(path: str) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def load_bell_schedule_file(path: str) -> BellSchedule:
    """Read and parse one bell schedule file."""
    try:
        data = _read_json(path)
    except OSError as err:
        raise BellScheduleError(
            f"{os.path.basename(path)} could not be opened: {err.strerror or err}"
        ) from None
    except ValueError as err:
        raise BellScheduleError(
            f"{os.path.basename(path)} is not valid JSON ({err}). A missing "
            f"comma or a stray quote is the usual cause."
        ) from None
    return parse_bell_schedule(data)


def load_section_map_file(path: str) -> SectionMap:
    """Read and parse one section-map file."""
    try:
        data = _read_json(path)
    except OSError as err:
        raise BellScheduleError(
            f"{os.path.basename(path)} could not be opened: {err.strerror or err}"
        ) from None
    except ValueError as err:
        raise BellScheduleError(
            f"{os.path.basename(path)} is not valid JSON ({err})."
        ) from None
    return parse_section_map(data)


def bell_schedule_folder() -> str | None:
    """The Library folder holding bell schedule files, or None with no workspace.

    One folder, `Library/Glass`, holds every file the display reads: the bell
    schedule, the section map, and the day plans in a subfolder.

    The import is lazy because `api.webui.config._io` pulls in `keyring`, and
    a pure schedule import should not drag a keyring backend along with it.
    """
    from api.webui import workspace

    return workspace.library_folder(BELL_SCHEDULE_FOLDER)


def _candidate_files(folder: str) -> list[str]:
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    return [
        os.path.join(folder, name)
        for name in names
        if name.lower().endswith(".json")
    ]


def _structural_problems(schedule: BellSchedule) -> list[str]:
    """Structural checks on a schedule that already parsed.

    Imported inside the call rather than at module scope only to keep the two
    sibling modules free to import each other's types later without a cycle.
    """
    from api.schedule.validate import validate

    return [str(problem) for problem in (validate(schedule) or [])]


def discover_bell_schedule() -> tuple[BellSchedule | None, list[str]]:
    """The bell schedule to run today, plus anything worth telling the teacher.

    Prefers a real file over a shipped sample. Returns None when there is
    nothing usable, always with at least one note explaining why, so the page
    can say something calm instead of showing an empty clock.
    """
    notes: list[str] = []
    folder = bell_schedule_folder()
    if not folder:
        return None, [
            "No workspace folder is set up yet, so there is no bell schedule to read."
        ]
    if not os.path.isdir(folder):
        return None, [
            f"No bell schedule yet. Add one to the Glass folder ({folder})."
        ]

    real: list[str] = []
    samples: list[str] = []
    for path in _candidate_files(folder):
        name = os.path.basename(path)
        try:
            data = _read_json(path)
        except (OSError, ValueError):
            notes.append(f"{name} could not be read as JSON, so it was skipped.")
            continue
        if not isinstance(data, dict):
            notes.append(f"{name} does not hold a set of fields, so it was skipped.")
            continue
        file_format = _text(data.get("format"))
        if file_format == SECTION_MAP_FORMAT:
            # A section map lives in the same folder and does a different job.
            continue
        if file_format != SCHEDULE_FORMAT:
            notes.append(
                f"{name} is not a bell schedule file, so it was skipped. A bell "
                f"schedule says its format is '{SCHEDULE_FORMAT}'."
            )
            continue
        (samples if data.get("sample") else real).append(path)

    if len(real) > 1:
        listed = ", ".join(sorted(os.path.basename(path) for path in real))
        notes.append(
            f"There is more than one bell schedule in the folder: {listed}. Glass "
            f"will not pick between them, so keep the one you use and move the "
            f"others somewhere else."
        )
        return None, notes

    chosen = real[0] if real else (samples[0] if samples else None)
    if chosen is None:
        notes.append(
            f"No bell schedule yet. Copy the template in the Glass folder "
            f"({folder}) and fill in your own bells."
        )
        return None, notes

    try:
        schedule = load_bell_schedule_file(chosen)
    except BellScheduleError as err:
        notes.append(f"{os.path.basename(chosen)}: {err}")
        return None, notes

    if schedule.is_sample:
        notes.append(
            "These are sample times from a made-up school, not your bells. To use "
            "your own, copy the sample or the template, fill in your times, and "
            "remove the \"sample\": true line."
        )
    notes.extend(_structural_problems(schedule))
    return schedule, notes


def load_section_map(path: str | None = None) -> tuple[SectionMap | None, list[str]]:
    """The section map, if the teacher has written one.

    Nothing reads this yet (see D4 in the build spec). It is loaded and
    validated so the file format is real and a later batch can rely on it.
    """
    if path is None:
        folder = bell_schedule_folder()
        if not folder:
            return None, [
                "No workspace folder is set up yet, so there is no section map to read."
            ]
        path = os.path.join(folder, SECTION_MAP_FILENAME)
    if not os.path.isfile(path):
        return None, [
            "No section map yet. It is optional, and nothing needs it to show the day."
        ]
    try:
        return load_section_map_file(path), []
    except BellScheduleError as err:
        return None, [f"{os.path.basename(path)}: {err}"]
