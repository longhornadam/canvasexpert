"""SmartDeck teacher-facing management page and API routes.

Routes:
  GET  /smartdeck                          -> renders templates/smartdeck.html
  GET  /smartdeck/api/decks                -> list active/archived decks + templates
  POST /smartdeck/api/decks/{id}/archive   -> archive a deck
  POST /smartdeck/api/decks/{id}/delete    -> delete a deck
  GET  /smartdeck/api/readiness            -> check schedule readiness for SmartDeck
  GET  /smartdeck/display/{deck_id}        -> renders display page (classroom projector)
  GET  /smartdeck/display/{deck_id}/data   -> returns display payload (JSON)
"""

from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from .. import deps, deck_store, schedule_setup

router = APIRouter(tags=["smartdeck"])


def _resolve_slides(deck: dict, blocks: list) -> tuple[list, list]:
    """Resolve a Deck's Slides against today's blocks.

    Returns (resolved_slides, problems). A Slide the display page could not show is
    dropped with a problem rather than raised on: display.js identifies Slides by id,
    so a missing or repeated id would make two Slides indistinguishable and wedge the
    rotation on whichever showed first. Decks are validated on save, so this only bites
    files edited by hand, which is a workflow the archive recovery path invites.
    """
    blocks_by_name = {b["name"]: b for b in blocks}
    widgets_by_id = {
        w["id"]: w for w in (deck.get("widgets") or [])
        if isinstance(w, dict) and w.get("id")
    }
    # A Deck can be for any date, so name it rather than saying "today".
    day = f"the schedule for {deck['date']}" if deck.get("date") else "this deck's schedule"

    resolved = []
    problems = []
    seen_ids = set()
    for position, slide in enumerate(deck.get("slides") or [], start=1):
        if not isinstance(slide, dict):
            problems.append(f"slide {position} is not a slide object, so it was skipped")
            continue

        slide_id = slide.get("id")
        if not slide_id:
            problems.append(f"slide {position} has no id, so it was skipped")
            continue
        if slide_id in seen_ids:
            problems.append(
                f"slide {slide_id!r} appears more than once; only the first was kept")
            continue
        seen_ids.add(slide_id)

        block = blocks_by_name.get(slide.get("block"))
        if block is None:
            problems.append(
                f"slide {slide_id!r}: block {slide.get('block')!r} is not in {day}, "
                f"so it will not appear")

        resolved.append({
            "id": slide_id,
            "block": slide.get("block"),
            "layout": slide.get("layout"),
            "title": slide.get("title", ""),
            "body": slide.get("body", ""),
            "widgets": [widgets_by_id[wid] for wid in (slide.get("widgets") or [])
                        if wid in widgets_by_id],
            "start": block["start"] if block else None,
            "end": block["end"] if block else None,
        })

    return resolved, problems


def _deck_problems(deck_id: str, date: str, schedule_cache: dict) -> list:
    """What would keep part of this Deck off the projector, for the management page.

    Shown next to Display so the teacher finds out before projecting rather than in
    front of a class. schedule_cache is per-request: resolve_schedule_for re-reads the
    calendar CSVs on every call, and a teacher can have a deck per school day.
    """
    deck, load_problems = deck_store.load_deck(deck_id)
    if deck is None:
        return load_problems

    if date not in schedule_cache:
        schedule_cache[date] = deps.resolve_schedule_for(date)
    blocks, schedule_problems = schedule_cache[date]

    _resolved, slide_problems = _resolve_slides(deck, blocks)
    return list(schedule_problems) + slide_problems


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

    # Only active decks carry a Display button, so only they need the warning.
    schedule_cache = {}
    for entry in active:
        entry["problems"] = _deck_problems(
            entry["deck_id"], entry.get("date", ""), schedule_cache)

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
    """Return the local class schedule readiness projection."""
    return JSONResponse({"ok": True, **schedule_setup.readiness()})


@router.get("/smartdeck/display/{deck_id}", response_class=HTMLResponse)
def smartdeck_display_page(request: Request, deck_id: str):
    """Classroom projector display page for a SmartDeck.

    Renders the display template; the JavaScript fetches the deck data
    from /smartdeck/display/{deck_id}/data once on load.
    """
    return deps.templates.TemplateResponse(request, "smartdeck_display.html", {
        "deck_id": deck_id,
    })


@router.get("/smartdeck/display/{deck_id}/data")
def smartdeck_display_data(deck_id: str):
    """Full display payload for a SmartDeck (resolved schedule, resolved widgets).

    This is the single data fetch the display page performs; no further
    network requests after initial page load.

    Returns {ok: bool, deck_id, date, title, server_time, slides, problems}
    where each slide contains full resolved widget objects {id, scope, kind, params}.
    """
    deck, problems = deck_store.load_deck(deck_id)
    if deck is None:
        return JSONResponse({"ok": False, "problems": problems}, status_code=404)

    blocks, schedule_problems = deps.resolve_schedule_for(deck.get("date", ""))
    resolved_slides, slide_problems = _resolve_slides(deck, blocks)
    slide_problems = list(schedule_problems) + slide_problems

    return JSONResponse({
        "ok": True,
        "deck_id": deck_id,
        "date": deck.get("date"),
        "title": deck.get("title"),
        "server_time": datetime.now().isoformat(timespec="seconds"),
        "slides": resolved_slides,
        "problems": slide_problems,
    })
