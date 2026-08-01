"""Class schedule setup APIs used by Settings and SmartDeck."""

import json
import re
from datetime import date

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from .. import config, deps, schedule_setup, workspace


router = APIRouter(tags=["schedule"])


@router.get("/api/schedule")
def get_schedule():
    readiness = schedule_setup.readiness()
    blocks, block_problems = schedule_setup.load_blocks()
    if block_problems:
        readiness["missing"].extend(problem for problem in block_problems
                                     if problem not in readiness["missing"])
        piece = readiness["pieces"]["teacher_schedule"]["problems"]
        piece.extend(problem for problem in schedule_setup.real_problems(block_problems)
                     if problem not in piece)
    return JSONResponse({
        "ok": True,
        **readiness,
        "blocks": blocks,
        "courses": [
            {
                "id": str(course["id"]),
                "name": config.course_display_name(course["id"]),
                "active": bool(course.get("active", True)),
            }
            for course in config.saved_courses()
        ],
        "folders": {
            "calendars": workspace.library_folder("Calendars"),
            "smartdecks": workspace.library_folder("SmartDecks"),
        },
    })


def _schedule_choice_label(label: str) -> str:
    """'Bell Schedule - Pep Rally' -> 'Pep Rally'.

    Every file carries the prefix, so under a control already labelled
    "Today's bell schedule" it is five identical words of noise in front of the
    one word that distinguishes the options.
    """
    trimmed = re.sub(r"^\s*bell\s+schedule\b[\s\-_]*", "", label, flags=re.I)
    return re.sub(r"\s+", " ", trimmed).strip() or label.strip()


@router.get("/api/schedule/today")
def get_schedule_today():
    """Which bell schedule today is running on, and what else is available.

    Bell schedules change more often than anyone updates a calendar, and a
    stale calendar does not fail loudly: it quietly resolves to the wrong
    class. This is the read behind the one-line correction on the Panels page.
    """
    today = date.today().isoformat()
    day_calendar, _problems = deps.load_day_calendar()
    overrides, _override_problems = schedule_setup.read_day_overrides()
    options = [
        {"schedule_id": entry["schedule_id"],
         "label": _schedule_choice_label(entry["label"])}
        for entry in deps.list_bell_schedule_files()
    ]
    schedule_id = day_calendar.get(today, "")
    labels = {option["schedule_id"]: option["label"] for option in options}
    return JSONResponse({
        "ok": True,
        "date": today,
        "schedule_id": schedule_id,
        "label": labels.get(schedule_id, ""),   # already prefix-stripped
        "corrected": today in overrides,
        # A schedule id with no matching file resolves to an empty day, which
        # on a wall is indistinguishable from a holiday. Say so instead.
        "unknown_schedule": bool(schedule_id) and schedule_id not in labels,
        "options": options,
    })


@router.post("/api/schedule/today")
def post_schedule_today(schedule_id: str = Form("")):
    """Correct today's bell schedule. An empty id clears the correction."""
    saved, problems = schedule_setup.set_day_override(
        date.today().isoformat(), schedule_id)
    if problems or saved is None:
        return JSONResponse({"ok": False, "problems": problems})
    return JSONResponse({"ok": True, **saved})


@router.post("/api/schedule/teacher")
def post_schedule_teacher(blocks: str = Form(...)):
    try:
        parsed = json.loads(blocks)
    except json.JSONDecodeError as exc:
        return JSONResponse({"ok": False, "problems": [f"blocks must be valid JSON: {exc}"]})
    if not isinstance(parsed, list):
        return JSONResponse({"ok": False, "problems": ["blocks must be a list"]})

    saved, problems = schedule_setup.save_blocks(parsed)
    if problems or saved is None:
        return JSONResponse({"ok": False, "problems": problems})
    return JSONResponse({
        "ok": True,
        "count": len(saved.get("blocks", [])),
        "path": schedule_setup.teacher_schedule_path(),
    })
