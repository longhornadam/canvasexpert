"""Class schedule setup APIs used by Settings and SmartDeck."""

import json

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from .. import config, schedule_setup


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
    })


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
