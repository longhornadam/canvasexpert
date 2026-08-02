"""Teacher class schedule setup.

This module owns the local schedule setup surface: readiness composition and the
Teacher Schedule JSON write path. It is kept separate from the cached network
readiness probe and from the gradebook calendar routes, even though both features
inspect the same workspace folder.
"""

import json
import os
import tempfile

from . import config, day_schedule, deps, workspace


# The loaders report a missing file or folder as a problem string. Each piece
# already carries `present`, and `missing` still lists these for the schedule, so
# repeating them per piece only duplicates whatever the panel says about absence.
_ABSENCE_PROBLEMS = frozenset({
    "no teacher schedule found",
    "no workspace Calendars folder found",
    "no bell schedules found",
})


def real_problems(problems) -> list:
    """Drop absence sentinels, keeping read and parse failures."""
    return [problem for problem in problems if problem not in _ABSENCE_PROBLEMS]


def _calendars_dir():
    return workspace.library_folder("Calendars")


def _calendars_dir():
    return workspace.library_folder("Calendars")


def teacher_schedule_path() -> str | None:
    calendars = _calendars_dir()
    return os.path.join(calendars, "Teacher Schedule.json") if calendars else None


def _compose_readiness(teacher_schedule, teacher_problems, bell_schedules, bell_problems):
    found = [
        {"name": entry["name"], "schedule_id": entry["schedule_id"]}
        for entry in deps.list_bell_schedule_files()
        if entry["schedule_id"] in bell_schedules
    ]
    teacher_blocks = teacher_schedule.get("blocks") if isinstance(teacher_schedule, dict) else []
    if not isinstance(teacher_blocks, list):
        teacher_blocks = []
    saved_course_ids = {
        str(course.get("id"))
        for course in config.saved_courses()
        if isinstance(course, dict) and course.get("id") is not None
    }
    unknown_course_ids = sorted({
        block.get("course_id")
        for block in teacher_blocks
        if isinstance(block, dict)
        and isinstance(block.get("course_id"), str)
        and block.get("course_id")
        and block.get("course_id") not in saved_course_ids
    })

    pieces = {
        "teacher_schedule": {
            "present": bool(teacher_schedule),
            "count": len(teacher_blocks),
            "path": teacher_schedule_path(),
            "problems": real_problems(teacher_problems),
            "unknown_course_ids": unknown_course_ids,
        },
        "bell_schedules": {
            "present": bool(bell_schedules),
            "count": len(bell_schedules),
            "path": _calendars_dir(),
            "found": found,
            "problems": real_problems(bell_problems),
        },
    }

    missing = list(teacher_problems) + list(bell_problems)
    if not teacher_schedule and not any("teacher schedule" in problem.lower() for problem in missing):
        missing.append("no teacher schedule found")
    if not bell_schedules and "no bell schedules found" not in missing:
        missing.append("no bell schedules found")

    return {
        "ready": bool(teacher_schedule) and bool(bell_schedules),
        "missing": missing,
        "pieces": pieces,
    }


def readiness() -> dict:
    """Compose the Teacher Schedule and Bell Schedule readiness payload.

    Whole-calendar readiness (coverage, today's resolution, low-coverage
    warning) is api/webui/school_calendar.py:readiness() -- the Calendar page
    composes both; this one stays scoped to what the Teacher Schedule editor
    and Bell Schedule list need.
    """
    teacher_schedule, teacher_problems = deps.load_teacher_schedule()
    bell_schedules, bell_problems = deps.load_bell_schedules()
    return _compose_readiness(teacher_schedule, teacher_problems, bell_schedules, bell_problems)


def load_blocks() -> tuple[list, list]:
    """Return the raw Teacher Schedule blocks and any read/parse problems."""
    data, problems = deps.load_teacher_schedule()
    blocks = data.get("blocks") if isinstance(data, dict) else []
    return (blocks if isinstance(blocks, list) else []), list(problems)


def _validate_block_periods_against_bell_schedules(blocks: list) -> list:
    """Reject teacher periods that do not exist in any workspace meeting list."""
    bell_schedules, _problems = deps.load_bell_schedules()
    known_periods = {
        str(meeting.get("period_id"))
        for meetings in bell_schedules.values()
        if isinstance(meetings, list)
        for meeting in meetings
        if isinstance(meeting, dict) and meeting.get("period_id") is not None
    }
    if not known_periods:
        return ["no bell schedules found; cannot validate teacher schedule periods"]

    problems = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        name = block.get("name") or ""
        for period in block.get("raw_periods") or []:
            period_id = str(period)
            if period_id not in known_periods:
                problems.append(
                    f"block '{name}': period '{period_id}' not found in any bell schedule"
                )
    return problems


def _validate_block_courses(blocks: list) -> list:
    """Reject a nonempty course_id that is not a Current (active) course.

    Calendar lists only Current courses as selectable Teacher Schedule
    bindings; a Previous or unknown course_id is rejected here rather than
    silently saved, whether the caller is the web UI or an MCP assistant --
    both routes call this same seam. An existing file naming a Previous/
    unknown course remains readable (see schedule_setup.readiness()); the
    teacher must choose a Current course or clear it before saving again.
    """
    active_ids = {
        str(course.get("id"))
        for course in config.active_courses()
        if isinstance(course, dict) and course.get("id") is not None
    }
    problems = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        course_id = block.get("course_id")
        if isinstance(course_id, str) and course_id and course_id not in active_ids:
            problems.append(
                f"block '{block.get('name', '')}': course_id '{course_id}' is not a "
                "Current course -- choose a Current course or clear it before saving")
    return problems


def save_blocks(blocks: list) -> tuple[dict | None, list]:
    """Validate and atomically replace only ``blocks`` in Teacher Schedule.json."""
    validation_problems = day_schedule.validate_teacher_schedule({"blocks": blocks})
    if validation_problems:
        return None, validation_problems

    path = teacher_schedule_path()
    calendars = _calendars_dir()
    if not path or not calendars:
        return None, ["no workspace available"]

    period_problems = _validate_block_periods_against_bell_schedules(blocks)
    if period_problems:
        return None, period_problems

    course_problems = _validate_block_courses(blocks)
    if course_problems:
        return None, course_problems

    data = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            return None, [f"could not read Teacher Schedule.json: {exc}"]
        if not isinstance(data, dict):
            return None, ["Teacher Schedule.json must contain an object"]

    if "version" not in data:
        data["version"] = "1.0-json"
    data["blocks"] = blocks

    os.makedirs(calendars, exist_ok=True)
    fd = None
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(
            prefix=".teacher_schedule_", suffix=".partial", dir=calendars, text=True
        )
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except (OSError, IOError) as exc:
        if temporary and os.path.exists(temporary):
            try:
                os.unlink(temporary)
            except OSError:
                pass
        return None, [f"failed to write Teacher Schedule.json: {exc}"]

    return data, []
