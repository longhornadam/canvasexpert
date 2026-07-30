"""SmartDeck teacher-facing management page and API routes.

Routes:
  GET  /smartdeck                          -> renders templates/smartdeck.html
  GET  /smartdeck/api/decks                -> list active/archived decks + templates
  POST /smartdeck/api/decks/{id}/archive   -> archive a deck
  POST /smartdeck/api/decks/{id}/delete    -> delete a deck
  GET  /smartdeck/api/readiness            -> check schedule readiness for SmartDeck
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from .. import deps, deck_store

router = APIRouter(tags=["smartdeck"])


@router.get("/smartdeck", response_class=HTMLResponse)
def smartdeck_page(request: Request):
    """SmartDeck management page — decks, templates, and configuration."""
    return deps.templates.TemplateResponse(request, "smartdeck.html", {
        "nav_section": "smartdeck",
    })


@router.get("/smartdeck/api/decks")
def smartdeck_list_decks():
    """List active decks, archived decks, and available templates.

    Returns {ok: True, active: [...], archived: [...], deck_templates: [...], slide_templates: [...]}
    """
    active = deck_store.list_decks("active")
    archived = deck_store.list_decks("archived")
    deck_templates = deck_store.list_templates("deck")
    slide_templates = deck_store.list_templates("slide")

    return JSONResponse({
        "ok": True,
        "active": active,
        "archived": archived,
        "deck_templates": deck_templates,
        "slide_templates": slide_templates,
    })


@router.post("/smartdeck/api/decks/{deck_id}/archive")
def smartdeck_archive_deck(deck_id: str):
    """Move a deck from active to archived.

    Returns {ok: bool, problems: [str]}
    """
    success, problems = deck_store.archive_deck(deck_id)
    return JSONResponse({
        "ok": success,
        "problems": problems,
    })


@router.post("/smartdeck/api/decks/{deck_id}/delete")
def smartdeck_delete_deck(deck_id: str):
    """Move a deck to the system Archive (soft delete, recoverable).

    Returns {ok: bool, problems: [str]}
    """
    success, problems = deck_store.delete_deck(deck_id)
    return JSONResponse({
        "ok": success,
        "problems": problems,
    })


@router.get("/smartdeck/api/readiness")
def smartdeck_readiness():
    """Check if all required schedules are configured for SmartDeck.

    Composes schedule readiness from three loaders in deps.py:
    - load_teacher_schedule()
    - load_bell_schedules()
    - load_day_calendar()

    Returns {ok: True, ready: bool, missing: [str]}
    """
    teacher_schedule, teacher_problems = deps.load_teacher_schedule()
    bell_schedules, bell_problems = deps.load_bell_schedules()
    day_calendar, day_cal_problems = deps.load_day_calendar()

    ready = bool(teacher_schedule) and bool(bell_schedules) and bool(day_calendar)
    missing = teacher_problems + bell_problems + day_cal_problems

    return JSONResponse({
        "ok": True,
        "ready": ready,
        "missing": missing,
    })
