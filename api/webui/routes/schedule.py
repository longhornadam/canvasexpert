"""Class schedule setup APIs used by Settings and SmartDeck."""

import json

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from .. import schedule_setup, workspace


router = APIRouter(tags=["schedule"])


def _response(result, problems):
    payload = dict(result or {})
    payload["problems"] = list(problems)
    payload["ok"] = bool(payload.get("ok", not problems)) and not problems
    return JSONResponse(payload)


@router.get("/api/schedule")
def get_schedule():
    readiness = schedule_setup.readiness()
    blocks, block_problems = schedule_setup.load_blocks()
    if block_problems:
        readiness["missing"].extend(problem for problem in block_problems
                                     if problem not in readiness["missing"])
        readiness["pieces"]["teacher_schedule"]["problems"].extend(
            problem for problem in block_problems
            if problem not in readiness["pieces"]["teacher_schedule"]["problems"]
        )
    return JSONResponse({
        "ok": True,
        **readiness,
        "blocks": blocks,
        "folders": {
            "calendars": workspace.library_folder("Calendars"),
            "smartdecks": workspace.library_folder("SmartDecks"),
        },
        "examples": schedule_setup.list_examples(),
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


@router.post("/api/schedule/examples/load")
def post_schedule_example_load(slug: str = Form(...), overwrite: bool = Form(False)):
    result, problems = schedule_setup.load_example(slug, overwrite=overwrite)
    if result is None:
        return JSONResponse({"ok": False, "problems": problems})
    return _response(result, problems)


@router.post("/api/schedule/examples/remove")
def post_schedule_example_remove(slug: str = Form(...)):
    result, problems = schedule_setup.remove_example(slug)
    if result is None:
        return JSONResponse({"ok": False, "problems": problems})
    return _response(result, problems)
