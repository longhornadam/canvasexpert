"""SmartDeck class schedule setup and example storage.

This module owns the local schedule setup surface: readiness composition, the
Teacher Schedule JSON write path, and the shipped example catalog. It is kept
separate from the cached network readiness probe and from the gradebook calendar
routes, even though both features inspect the same workspace folder.
"""

import json
import os
import shutil
import tempfile
from datetime import datetime

from . import deck_schedule, deps, workspace


EXAMPLES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "default_docs", "Examples", "Class Schedules")
)


def _calendars_dir():
    return workspace.library_folder("Calendars")


def _smartdecks_dir():
    return workspace.library_folder("SmartDecks")


def teacher_schedule_path() -> str | None:
    smartdecks = _smartdecks_dir()
    return os.path.join(smartdecks, "Teacher Schedule.json") if smartdecks else None


def _day_calendar_files():
    calendars = _calendars_dir()
    if not calendars or not os.path.isdir(calendars):
        return []

    found = []
    for filename in sorted(os.listdir(calendars)):
        if not filename.lower().endswith(".csv") or filename.lower().startswith("bell schedule"):
            continue
        path = os.path.join(calendars, filename)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                content = handle.read()
        except OSError:
            continue
        lines = content.strip().splitlines()
        if not lines:
            continue
        header = {field.strip().lower() for field in lines[0].split(",")}
        if {"date", "schedule_id"} <= header:
            found.append(filename)
    return found


def _day_calendar_detail(day_calendar, bell_schedules):
    dates = sorted(day_calendar)
    schedule_ids = sorted(set(day_calendar.values()))
    return {
        "present": bool(day_calendar),
        "count": len(dates),
        "date_count": len(dates),
        "path": _calendars_dir(),
        "files": _day_calendar_files(),
        "schedule_ids": schedule_ids,
        "unknown_schedule_ids": sorted(set(schedule_ids) - set(bell_schedules)),
        "first": dates[0] if dates else None,
        "last": dates[-1] if dates else None,
    }


def _compose_readiness(teacher_schedule, teacher_problems, bell_schedules,
                       bell_problems, day_calendar, day_problems):
    bell_files = deps.list_bell_schedule_files()
    found = [
        {
            "name": entry["name"],
            "label": entry["label"],
            "schedule_id": entry["schedule_id"],
            "period_count": len(bell_schedules.get(entry["schedule_id"], [])),
        }
        for entry in bell_files
        if entry["schedule_id"] in bell_schedules
    ]
    teacher_blocks = teacher_schedule.get("blocks") if isinstance(teacher_schedule, dict) else []
    if not isinstance(teacher_blocks, list):
        teacher_blocks = []

    pieces = {
        "teacher_schedule": {
            "present": bool(teacher_schedule),
            "count": len(teacher_blocks),
            "block_count": len(teacher_blocks),
            "path": teacher_schedule_path(),
            "problems": list(teacher_problems),
        },
        "bell_schedules": {
            "present": bool(bell_schedules),
            "count": len(bell_schedules),
            "path": _calendars_dir(),
            "found": found,
            "problems": list(bell_problems),
        },
        "day_calendar": {
            **_day_calendar_detail(day_calendar, bell_schedules),
            "problems": list(day_problems),
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


def _example_dir(slug):
    if not isinstance(slug, str) or not slug:
        return None
    for path in _example_dirs():
        if path.name == slug:
            return path
    return None


def _example_dirs():
    if not os.path.isdir(EXAMPLES_DIR):
        return []
    return sorted(
        (entry for entry in os.scandir(EXAMPLES_DIR) if entry.is_dir()),
        key=lambda entry: entry.name,
    )


def _read_manifest(example_dir):
    path = os.path.join(example_dir, "manifest.json")
    try:
        with open(path, encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(manifest, dict):
        return None
    return manifest


def _example_files(manifest):
    return [manifest["teacher_schedule"], *manifest["bell_schedules"], manifest["day_calendar"]]


def _workspace_example_path(filename):
    if filename == "Teacher Schedule.json":
        base = _smartdecks_dir()
    else:
        base = _calendars_dir()
    return os.path.join(base, filename) if base else None


def list_examples() -> list[dict]:
    """Return the shipped example manifests and whether each is loaded."""
    examples = []
    for entry in _example_dirs():
        manifest = _read_manifest(entry.path)
        if not manifest:
            continue
        files = _example_files(manifest)
        loaded = all(
            _workspace_example_path(filename) and os.path.isfile(_workspace_example_path(filename))
            for filename in files
        )
        examples.append({
            **manifest,
            "slug": manifest.get("slug", entry.name),
            "dir": entry.path,
            "loaded": loaded,
        })
    return examples


def _replacement_path(path):
    directory, filename = os.path.split(path)
    stem, extension = os.path.splitext(filename)
    stamp = datetime.now().strftime("%Y-%m-%d %H%M")
    candidate = os.path.join(directory, f"{stem} (replaced {stamp}){extension}")
    suffix = 2
    while os.path.exists(candidate):
        candidate = os.path.join(directory, f"{stem} (replaced {stamp} {suffix}){extension}")
        suffix += 1
    return candidate


def _move_aside(path):
    destination = _replacement_path(path)
    try:
        shutil.move(path, destination)
    except (OSError, shutil.Error) as exc:
        return None, f"could not move {os.path.basename(path)} aside: {exc}"
    return destination, None


def load_example(slug, overwrite=False) -> tuple[dict | None, list]:
    """Copy a shipped example into the workspace, moving conflicts aside when asked."""
    example_dir = _example_dir(slug)
    if not example_dir:
        return None, [f"unknown schedule example: {slug}"]
    manifest = _read_manifest(example_dir.path)
    if not manifest:
        return None, [f"invalid schedule example manifest: {slug}"]

    files = _example_files(manifest)
    source_paths = [os.path.join(example_dir.path, filename) for filename in files]
    missing_sources = [filename for filename, path in zip(files, source_paths) if not os.path.isfile(path)]
    if missing_sources:
        return None, [f"example is missing: {filename}" for filename in missing_sources]

    teacher_path = teacher_schedule_path()
    calendars = _calendars_dir()
    smartdecks = _smartdecks_dir()
    if not teacher_path or not calendars or not smartdecks:
        return None, ["no workspace available"]

    existing_teacher = os.path.isfile(teacher_path)
    if existing_teacher and not overwrite:
        return {
            "ok": False,
            "slug": slug,
            "conflict": "teacher_schedule",
            "written": [],
            "skipped": [],
            "moved_aside": [],
            "day_calendar_overlap": 0,
        }, ["Teacher Schedule.json already exists"]

    existing_days, _ = deps.load_day_calendar()
    with open(os.path.join(example_dir.path, manifest["day_calendar"]), encoding="utf-8") as handle:
        example_day, day_problems = deck_schedule.parse_day_calendar(handle.read())
    if day_problems:
        return None, day_problems

    result = {
        "ok": True,
        "slug": slug,
        "written": [],
        "skipped": [],
        "moved_aside": [],
        "day_calendar_overlap": len(set(existing_days) & set(example_day)),
    }

    os.makedirs(calendars, exist_ok=True)
    os.makedirs(smartdecks, exist_ok=True)
    for filename, source in zip(files, source_paths):
        target = _workspace_example_path(filename)
        if os.path.isfile(target):
            if not overwrite:
                result["skipped"].append(filename)
                continue
            moved, problem = _move_aside(target)
            if problem:
                return None, [problem]
            result["moved_aside"].append(os.path.basename(moved))
        try:
            shutil.copy2(source, target)
        except (OSError, shutil.Error) as exc:
            return None, [f"could not copy {filename}: {exc}"]
        result["written"].append(filename)

    return result, []


def remove_example(slug) -> tuple[dict | None, list]:
    """Move unchanged example files to the system archive and keep edited files."""
    example_dir = _example_dir(slug)
    if not example_dir:
        return None, [f"unknown schedule example: {slug}"]
    manifest = _read_manifest(example_dir.path)
    if not manifest:
        return None, [f"invalid schedule example manifest: {slug}"]

    archive_root = workspace.system_folder("Archive")
    if not archive_root:
        return None, ["no workspace available"]
    archive_dir = os.path.join(archive_root, "Class Schedule Examples", slug)
    result = {"ok": True, "slug": slug, "moved": [], "kept": []}

    for filename in _example_files(manifest):
        current = _workspace_example_path(filename)
        shipped = os.path.join(example_dir.path, filename)
        if not current or not os.path.isfile(current):
            continue
        try:
            with open(current, "rb") as current_handle, open(shipped, "rb") as shipped_handle:
                unchanged = current_handle.read() == shipped_handle.read()
        except OSError as exc:
            return None, [f"could not read {filename}: {exc}"]
        if not unchanged:
            result["kept"].append(filename)
            continue

        destination = os.path.join(archive_dir, filename)
        if os.path.exists(destination):
            return None, [f"archive already contains {filename}"]
        try:
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            shutil.move(current, destination)
        except (OSError, shutil.Error) as exc:
            return None, [f"could not archive {filename}: {exc}"]
        result["moved"].append(filename)

    return result, []
