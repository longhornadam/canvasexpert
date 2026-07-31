"""SmartDeck class schedule setup.

This module owns the local schedule setup surface: readiness composition and the
Teacher Schedule JSON write path. It is kept separate from the cached network
readiness probe and from the gradebook calendar routes, even though both features
inspect the same workspace folder.
"""

import json
import os
import tempfile

from . import deck_schedule, deps, workspace


# The loaders report a missing file or folder as a problem string. Each piece
# already carries `present`, and `missing` still lists these for SmartDeck, so
# repeating them per piece only duplicates whatever the panel says about absence.
_ABSENCE_PROBLEMS = frozenset({
    "no teacher schedule found",
    "no workspace SmartDecks folder found",
    "no workspace Calendars folder found",
    "no bell schedules found",
})


def real_problems(problems) -> list:
    """Drop absence sentinels, keeping read and parse failures."""
    return [problem for problem in problems if problem not in _ABSENCE_PROBLEMS]


def _calendars_dir():
    return workspace.library_folder("Calendars")


def _smartdecks_dir():
    return workspace.library_folder("SmartDecks")


def teacher_schedule_path() -> str | None:
    smartdecks = _smartdecks_dir()
    return os.path.join(smartdecks, "Teacher Schedule.json") if smartdecks else None


def _day_calendar_detail(day_calendar, bell_schedules):
    dates = sorted(day_calendar)
    schedule_ids = set(day_calendar.values())
    return {
        "present": bool(day_calendar),
        "count": len(dates),
        "path": _calendars_dir(),
        "unknown_schedule_ids": sorted(schedule_ids - set(bell_schedules)),
        "first": dates[0] if dates else None,
        "last": dates[-1] if dates else None,
    }


def _compose_readiness(teacher_schedule, teacher_problems, bell_schedules,
                       bell_problems, day_calendar, day_problems):
    found = [
        {"name": entry["name"], "schedule_id": entry["schedule_id"]}
        for entry in deps.list_bell_schedule_files()
        if entry["schedule_id"] in bell_schedules
    ]
    teacher_blocks = teacher_schedule.get("blocks") if isinstance(teacher_schedule, dict) else []
    if not isinstance(teacher_blocks, list):
        teacher_blocks = []

    pieces = {
        "teacher_schedule": {
            "present": bool(teacher_schedule),
            "count": len(teacher_blocks),
            "path": teacher_schedule_path(),
            "problems": real_problems(teacher_problems),
        },
        "bell_schedules": {
            "present": bool(bell_schedules),
            "count": len(bell_schedules),
            "path": _calendars_dir(),
            "found": found,
            "problems": real_problems(bell_problems),
        },
        "day_calendar": {
            **_day_calendar_detail(day_calendar, bell_schedules),
            "problems": real_problems(day_problems),
        },
    }

    missing = list(teacher_problems) + list(bell_problems) + list(day_problems)
    if not teacher_schedule and not any("teacher schedule" in problem.lower() for problem in missing):
        missing.append("no teacher schedule found")
    if not bell_schedules and "no bell schedules found" not in missing:
        missing.append("no bell schedules found")
    if not day_calendar and not any("day calendar" in problem.lower() for problem in missing):
        missing.append("no day calendar found")

    return {
        "ready": bool(teacher_schedule) and bool(bell_schedules) and bool(day_calendar),
        "missing": missing,
        "pieces": pieces,
    }


def readiness() -> dict:
    """Compose the three local schedule inputs into one readiness payload."""
    teacher_schedule, teacher_problems = deps.load_teacher_schedule()
    bell_schedules, bell_problems = deps.load_bell_schedules()
    day_calendar, day_problems = deps.load_day_calendar()
    return _compose_readiness(
        teacher_schedule, teacher_problems,
        bell_schedules, bell_problems,
        day_calendar, day_problems,
    )


def load_blocks() -> tuple[list, list]:
    """Return the raw Teacher Schedule blocks and any read/parse problems."""
    data, problems = deps.load_teacher_schedule()
    blocks = data.get("blocks") if isinstance(data, dict) else []
    return (blocks if isinstance(blocks, list) else []), list(problems)


def save_blocks(blocks: list) -> tuple[dict | None, list]:
    """Replace only ``blocks`` in Teacher Schedule.json, atomically."""
    validation_problems = deck_schedule.validate_teacher_schedule({"blocks": blocks})
    if validation_problems:
        return None, validation_problems

    path = teacher_schedule_path()
    smartdecks = _smartdecks_dir()
    if not path or not smartdecks:
        return None, ["no workspace available"]

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

    os.makedirs(smartdecks, exist_ok=True)
    fd = None
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(
            prefix=".teacher_schedule_", suffix=".partial", dir=smartdecks, text=True
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
