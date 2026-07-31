"""SmartDeck class schedule setup.

This module owns the local schedule setup surface: readiness composition and the
Teacher Schedule JSON write path. It is kept separate from the cached network
readiness probe and from the gradebook calendar routes, even though both features
inspect the same workspace folder.
"""

import csv
import glob
import json
import os
import re
import tempfile
from datetime import date, datetime, timedelta

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
        # A day calendar lists school days only -- weekends and holidays are
        # absent by design -- so "today is missing" says nothing about health.
        # Running past its last date is the condition worth reporting.
        "ends_before_today": bool(dates) and dates[-1] < date.today().isoformat(),
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


def _parse_schedule_date(value, field_name: str) -> tuple[date | None, str | None]:
    if isinstance(value, datetime):
        return None, f"{field_name} must be a YYYY-MM-DD date"
    if isinstance(value, date):
        return value, None
    if not isinstance(value, str):
        return None, f"{field_name} must be a YYYY-MM-DD date"
    try:
        parsed = date.fromisoformat(value.strip())
    except ValueError:
        return None, f"{field_name} must be a YYYY-MM-DD date"
    return parsed, None


def _normalize_date_rules(values, field_name: str) -> tuple[dict, list]:
    normalized = {}
    problems = []
    if values is None:
        return normalized, problems
    if not isinstance(values, dict):
        return normalized, [f"{field_name} must be an object"]
    for raw_date, schedule_id in values.items():
        parsed, problem = _parse_schedule_date(raw_date, f"{field_name} date")
        if problem:
            problems.append(problem)
            continue
        normalized[parsed.isoformat()] = schedule_id
    return normalized, problems


def _normalize_weekday_rules(values) -> tuple[dict, list]:
    normalized = {}
    problems = []
    if values is None:
        return normalized, problems
    if not isinstance(values, dict):
        return normalized, ["weekday_schedules must be an object"]
    for raw_weekday, schedule_id in values.items():
        try:
            weekday = int(raw_weekday)
        except (TypeError, ValueError):
            problems.append(f"weekday_schedules key '{raw_weekday}' must be 0 through 4")
            continue
        if isinstance(raw_weekday, bool) or weekday < 0 or weekday > 4:
            problems.append(f"weekday_schedules key '{raw_weekday}' must be 0 through 4")
            continue
        if weekday in normalized:
            problems.append(f"weekday_schedules contains duplicate key {weekday}")
            continue
        normalized[weekday] = schedule_id
    return normalized, problems


def _day_calendar_file_mappings(cal_dir: str) -> list[tuple[str, dict]]:
    found = []
    for path in sorted(glob.glob(os.path.join(cal_dir, "*.csv"))):
        filename = os.path.basename(path)
        if filename.lower().startswith("bell schedule"):
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                content = handle.read()
        except OSError:
            continue
        lines = content.strip().splitlines()
        if not lines:
            continue
        header = lines[0].lower()
        if "date" not in header or "schedule_id" not in header:
            continue
        mapping, _problems = deck_schedule.parse_day_calendar(content)
        found.append((filename, mapping))
    return found


def _day_calendar_overlap(cal_dir: str, target_filename: str,
                          generated_dates: set[str]) -> dict:
    existing = [
        (filename, mapping)
        for filename, mapping in _day_calendar_file_mappings(cal_dir)
        if filename != target_filename
    ]
    overlap_dates = set()
    winner_files = set()
    for generated_date in generated_dates:
        covering = [
            filename for filename, mapping in existing
            if generated_date in mapping
        ]
        if not covering:
            continue
        overlap_dates.add(generated_date)
        winner_files.add(max([target_filename, *covering]))
    return {"count": len(overlap_dates), "files": sorted(winner_files)}


def _write_day_calendar(path: str, rows: list[tuple[str, str]]) -> list:
    cal_dir = os.path.dirname(path)
    fd = None
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(
            prefix=".day_calendar_", suffix=".partial", dir=cal_dir, text=True
        )
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["date", "schedule_id"])
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except (OSError, IOError) as exc:
        if temporary and os.path.exists(temporary):
            try:
                os.unlink(temporary)
            except OSError:
                pass
        return [f"failed to write day calendar: {exc}"]
    return []


def _move_day_calendar_aside(path: str) -> tuple[str | None, list]:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    aside = f"{path}.{stamp}.bak"
    suffix = 1
    while os.path.exists(aside):
        aside = f"{path}.{stamp}.{suffix}.bak"
        suffix += 1
    try:
        os.rename(path, aside)
    except (OSError, IOError) as exc:
        return None, [f"failed to move existing day calendar aside: {exc}"]
    return aside, []


def save_day_calendar(label, start_date, end_date, default_schedule_id,
                      weekday_schedules=None, date_schedules=None,
                      skip_dates=None, replace=False) -> tuple[dict | None, list]:
    """Generate and atomically save one named day calendar CSV."""
    if not isinstance(label, str) or not label.strip():
        return None, ["label must be a non-empty string"]
    clean_label = label.strip()
    if any(separator in clean_label for separator in ("/", "\\")):
        return None, ["label must not contain a path separator"]
    normalized_label = re.sub(r"[^a-z0-9]+", "_", clean_label.lower()).strip("_")
    if normalized_label.startswith("bell_schedule"):
        return None, ["label must not normalize to a bell schedule prefix"]

    start, problem = _parse_schedule_date(start_date, "start_date")
    if problem:
        return None, [problem]
    end, problem = _parse_schedule_date(end_date, "end_date")
    if problem:
        return None, [problem]
    if start > end:
        return None, ["start_date must not be after end_date"]

    weekday_rules, problems = _normalize_weekday_rules(weekday_schedules)
    date_rules, date_rule_problems = _normalize_date_rules(date_schedules, "date_schedules")
    problems.extend(date_rule_problems)
    skip_values = set()
    if skip_dates is not None:
        if not isinstance(skip_dates, (list, tuple, set)):
            problems.append("skip_dates must be a list")
        else:
            for index, raw_date in enumerate(skip_dates):
                parsed, date_problem = _parse_schedule_date(
                    raw_date, f"skip_dates[{index}]"
                )
                if date_problem:
                    problems.append(date_problem)
                    continue
                skip_values.add(parsed.isoformat())

    if problems:
        return None, problems

    range_dates = set()
    cursor = start
    while cursor <= end:
        range_dates.add(cursor.isoformat())
        cursor += timedelta(days=1)
    out_of_range = sorted(
        date_value for date_value in skip_values.union(date_rules)
        if date_value < start.isoformat() or date_value > end.isoformat()
    )
    if out_of_range:
        return None, [
            "skip_dates and date_schedules must stay within the requested range: "
            + ", ".join(out_of_range)
        ]

    rows = []
    for date_value in sorted(range_dates):
        parsed = date.fromisoformat(date_value)
        if parsed.weekday() >= 5 or date_value in skip_values:
            continue
        if date_value in date_rules:
            schedule_id = date_rules[date_value]
        elif parsed.weekday() in weekday_rules:
            schedule_id = weekday_rules[parsed.weekday()]
        else:
            schedule_id = default_schedule_id
        rows.append((date_value, schedule_id))

    if not rows:
        return None, ["the requested range produces no school days"]

    if any(not isinstance(schedule_id, str) or not schedule_id.strip()
           for _date_value, schedule_id in rows):
        return None, ["every resulting schedule_id must be a non-empty string"]

    bell_schedules, bell_problems = deps.load_bell_schedules()
    schedule_ids = {schedule_id for _date_value, schedule_id in rows}
    unknown = sorted(
        (schedule_id for schedule_id in schedule_ids if schedule_id not in bell_schedules),
        key=lambda value: str(value),
    )
    if unknown:
        available = ", ".join(sorted(bell_schedules)) or "none"
        unknown_text = ", ".join(str(value) for value in unknown)
        return None, [
            f"unknown schedule_id(s): {unknown_text}; available schedule_id(s): {available}"
        ]
    if bell_problems:
        return None, list(bell_problems)

    cal_dir = _calendars_dir()
    if not cal_dir:
        return None, ["no workspace available"]
    try:
        os.makedirs(cal_dir, exist_ok=True)
    except OSError as exc:
        return None, [f"could not create Calendars folder: {exc}"]

    target_filename = f"Day Calendar {clean_label}.csv"
    target_path = os.path.join(cal_dir, target_filename)
    if os.path.exists(target_path) and not replace:
        return None, [
            f"day calendar already exists: {target_path}; pass replace=True to replace it"
        ]

    overlap = _day_calendar_overlap(
        cal_dir, target_filename, {date_value for date_value, _schedule_id in rows}
    )
    if os.path.exists(target_path) and replace:
        _aside_path, move_problems = _move_day_calendar_aside(target_path)
        if move_problems:
            return None, move_problems

    write_problems = _write_day_calendar(target_path, rows)
    if write_problems:
        return None, write_problems
    return {
        "ok": True,
        "path": os.path.abspath(target_path),
        "count": len(rows),
        "first": rows[0][0],
        "last": rows[-1][0],
        "overlap": overlap,
    }, []
