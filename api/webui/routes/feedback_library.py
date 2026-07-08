"""FeedbackExpert persona and feedback-pattern routes."""
import json

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from .. import config

router = APIRouter()


@router.get("/personas")
def list_personas():
    return JSONResponse({"personas": config.list_personas()})


@router.post("/personas/custom")
def add_custom_persona(persona_id: str = Form(""), name: str = Form(""),
                       personality: str = Form("")):
    config.save_custom_persona(persona_id.strip(), name.strip(), personality.strip())
    return JSONResponse({"ok": True, "personas": config.list_personas()})


@router.delete("/personas/custom")
def delete_custom_persona(persona_id: str = Form("")):
    config.remove_custom_persona(persona_id.strip())
    return JSONResponse({"ok": True, "personas": config.list_personas()})


@router.get("/patterns")
def list_patterns():
    return JSONResponse({"patterns": config.list_feedback_patterns()})


@router.post("/patterns")
def save_patterns(patterns: str = Form()):
    """Replace all feedback patterns with the provided JSON list."""
    try:
        parsed = json.loads(patterns)
        if not isinstance(parsed, list):
            return JSONResponse({"ok": False, "error": "Must be a JSON array."})
        config.set_feedback_patterns(parsed)
        return JSONResponse({"ok": True, "patterns": config.list_feedback_patterns()})
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": str(e)})
