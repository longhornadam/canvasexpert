"""Gradebook extra-time roster and tier-tag routes."""
import json

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from .. import config
from .gradebook_common import _course_students

router = APIRouter(tags=["gradebook"])


@router.get("/api/students/list")
def list_students(course_id: str):
    students, err = _course_students(course_id)
    if err:
        return JSONResponse({"ok": False, "error": err})
    out = sorted(
        ({"id": str(s["id"]),
          "name": s.get("sortable_name") or s.get("name", "")} for s in students),
        key=lambda s: s["name"].lower())
    return JSONResponse({"ok": True, "students": out})


@router.get("/api/extra-time")
def get_extra_time(course_id: str):
    return JSONResponse({"ok": True,
                         "students": config.get_extra_time(course_id),
                         "sweep_settings": config.get_sweep_settings()})


@router.post("/api/extra-time")
def save_extra_time(course_id: str = Form(...), students: str = Form(...)):
    try:
        config.set_extra_time(course_id, json.loads(students))
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": str(e)})
    return JSONResponse({"ok": True})


@router.get("/api/tier-tags")
def get_tier_tags_route():
    return JSONResponse({"ok": True, "tier_tags": config.get_tier_tags()})


@router.post("/api/tier-tags")
def save_tier_tags(tags: str = Form(...)):
    try:
        config.set_tier_tags(json.loads(tags))
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": f"bad request: {e}"})
    return JSONResponse({"ok": True, "tier_tags": config.get_tier_tags()})
