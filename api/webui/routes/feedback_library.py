"""Feedback tools persona and feedback-pattern routes."""
import json

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from api.platform_services import config

router = APIRouter()


def _valid_persona_id(value: str) -> bool:
    return bool(value) and all(char.islower() or char.isdigit() or char == "_" for char in value)


def _validate_patterns(patterns: list) -> str | None:
    seen = set()
    for pattern in patterns:
        if not isinstance(pattern, dict):
            return "Each feedback pattern must be an object."
        identifier = str(pattern.get("id") or "")
        if not _valid_persona_id(identifier) or identifier in seen or not str(pattern.get("name") or "").strip():
            return "Each feedback pattern needs a unique lowercase ID and a name."
        seen.add(identifier)
        for key in ("glows", "grows", "strategy_sentences"):
            bounds = pattern.get(key) or {}
            try:
                minimum, maximum = int(bounds.get("min")), int(bounds.get("max"))
            except (TypeError, ValueError):
                return "Each feedback pattern needs whole-number min/max bounds."
            if minimum < 0 or maximum < minimum or maximum > 10:
                return "Feedback-pattern bounds must be between 0 and 10."
    return None


@router.get("/personas")
def list_personas():
    return JSONResponse({"personas": config.list_personas()})


@router.post("/personas/custom")
def add_custom_persona(persona_id: str = Form(""), name: str = Form(""),
                       personality: str = Form("")):
    if not _valid_persona_id(persona_id.strip()) or not name.strip() or not personality.strip():
        return JSONResponse({"ok": False, "error": "Use a lowercase ID plus a name and personality."})
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
        error = _validate_patterns(parsed)
        if error:
            return JSONResponse({"ok": False, "error": error})
        config.set_feedback_patterns(parsed)
        return JSONResponse({"ok": True, "patterns": config.list_feedback_patterns()})
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": str(e)})
