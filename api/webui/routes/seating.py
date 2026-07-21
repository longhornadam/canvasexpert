"""Local-only API for Seating's physical layouts and manual assignments."""

from __future__ import annotations

import json

from fastapi import APIRouter, Form, Query
from fastapi.responses import JSONResponse

from api import seating_state
from .. import config


router = APIRouter(prefix="/api/seating", tags=["seating"])


@router.get("")
def seating_get(course_id: str = Query("")):
    """Return one course's local physical Seating state; never reads Canvas."""
    if not course_id:
        return JSONResponse({"ok": False, "error": "course_id required."})
    return JSONResponse({
        "ok": True,
        "state": seating_state.normalize_state(config.get_seating_course_state(course_id)),
    })


@router.post("/state")
def seating_state_update(
    course_id: str = Form(...),
    state: str = Form(...),
):
    """Atomically replace a validated local Seating state; never reads Canvas."""
    if not course_id:
        return JSONResponse({"ok": False, "error": "course_id required."})
    try:
        candidate = json.loads(state)
    except json.JSONDecodeError as error:
        return JSONResponse({"ok": False, "error": f"Invalid seating state JSON: {error}"})
    validated, error = seating_state.validate_state(candidate)
    if error:
        return JSONResponse({"ok": False, "error": error})
    config.set_seating_course_state(course_id, validated)
    return JSONResponse({"ok": True, "state": validated})
