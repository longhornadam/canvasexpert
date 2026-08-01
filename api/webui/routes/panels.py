"""Panels: standalone, embeddable views of local CanvasExpert data.

A Panel is one URL that renders one thing, full-bleed and responsive, with no
CanvasExpert chrome around it. It is meant to be dropped into whatever surface
the teacher already uses (a Classroomscreen Embed widget, a browser tab
fullscreened on a second monitor, an OBS browser source) so the display
surface stays swappable and no single host is load-bearing.

Two properties hold this together and are easy to break by accident:

* Panels are DISK-ONLY. They render unattended on a projector for a whole
  period, so a live Canvas call here would put network latency and token
  failures on a classroom wall. Every Panel reads the local catalog or mirror
  and says plainly when that data is missing, rather than reaching out.

* The port and the URL shape are PUBLIC CONTRACT. A teacher pastes
  ``http://127.0.0.1:8765/panels/whats-due?course=123`` into a board they
  save, and that string has to still work after restarts and upgrades. Do not
  add "helpfully pick a free port" fallback to the launcher, and do not move
  Panels onto generated ids: both silently kill every saved board weeks later.

Panel kinds live in PANEL_CATALOG, which is an allowlist. Unknown kinds 404
rather than rendering something improvised, for the same reason SmartDeck has
three fixed layouts: a closed set is what keeps this from sprawling.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from api.course_catalog import read_catalog
from api.mirror import read_service
from api.webui import config, deps

router = APIRouter()

DEFAULT_LOOKAHEAD_DAYS = 7
MAX_LOOKAHEAD_DAYS = 31

PANEL_CATALOG = {
    "whats-due": {
        "title": "What's due",
        "blurb": "Upcoming assignment due dates for one course. No student data.",
        "template": "panel_whats_due.html",
        "needs_course": True,
    },
}


def _parse_due(value):
    """A Canvas ``due_at`` as an aware UTC datetime, or None when absent or
    unparseable. Assignments with no due date are not late, they are simply
    not part of a due-date panel."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def whats_due_payload(course_id: str, days: int, *, now=None,
                      catalog_reader=None) -> dict:
    """Published assignments due between now and ``days`` out, soonest first.

    Always ``ok``: a Panel on a wall has no way to report an exception, so
    every outcome is a named ``state`` the template can render calmly.
    ``now`` and ``catalog_reader`` are injected by tests.
    """
    now = now or datetime.now(timezone.utc)
    days = max(1, min(int(days), MAX_LOOKAHEAD_DAYS))

    if not course_id:
        return {"ok": True, "state": "no_course", "days": days,
                "assignments": [],
                "message": "Choose a course for this panel."}

    reader = catalog_reader or (lambda cid: read_catalog(cid))
    read_result = reader(course_id)
    scope = read_service.catalog_assignments(course_id, catalog_reader=reader)

    if scope.get("source") == "none":
        return {"ok": True, "state": "no_catalog", "days": days,
                "assignments": [],
                "message": "No local course catalog yet. Refresh it in "
                           "CanvasExpert, then this panel fills in."}

    catalog = (read_result or {}).get("catalog") or {}
    horizon = now + timedelta(days=days)

    items = []
    for record in scope.get("records") or []:
        if not isinstance(record, dict):
            continue
        if not record.get("published", True):
            continue
        due = _parse_due(record.get("due_at"))
        if due is None or due < now or due > horizon:
            continue
        items.append({
            "title": str(record.get("name") or "Untitled assignment"),
            "due_at": due.isoformat(),
            "points": record.get("points_possible"),
        })
    items.sort(key=lambda item: item["due_at"])

    return {
        "ok": True,
        "state": "ready" if items else "nothing_due",
        "days": days,
        "course_name": str(catalog.get("course_name") or ""),
        "synced_at": scope.get("last_success_at", ""),
        "stale": scope.get("state") != "current",
        "assignments": items,
        "message": "" if items else f"Nothing due in the next {days} days.",
    }


@router.get("/panels", response_class=HTMLResponse)
def panels_page(request: Request):
    """Console: pick a Panel, point it at a course, copy the embed code."""
    courses = [
        {"id": str(c.get("id", "")), "name": str(c.get("name", "")) or f"Course {c.get('id', '')}"}
        for c in (config.saved_courses() or [])
    ]
    panels = [dict(spec, kind=kind) for kind, spec in sorted(PANEL_CATALOG.items())]
    return deps.templates.TemplateResponse(request, "panels.html", {
        "panels": panels,
        "courses": courses,
        "default_days": DEFAULT_LOOKAHEAD_DAYS,
    })


@router.get("/panels/{kind}", response_class=HTMLResponse)
def panel_page(request: Request, kind: str):
    """One Panel, chrome-free, sized to whatever box it is dropped into."""
    spec = PANEL_CATALOG.get(kind)
    if spec is None:
        return HTMLResponse(f"Unknown panel: {kind}", status_code=404)
    return deps.templates.TemplateResponse(request, spec["template"], {
        "kind": kind,
        "panel_title": spec["title"],
    })


@router.get("/panels/{kind}/data")
def panel_data(kind: str, course: str = "", days: int = DEFAULT_LOOKAHEAD_DAYS):
    """The Panel's single data fetch. Disk-only; never calls Canvas."""
    if kind not in PANEL_CATALOG:
        return JSONResponse({"ok": False, "error": f"Unknown panel: {kind}"},
                            status_code=404)
    if kind == "whats-due":
        return JSONResponse(whats_due_payload(course, days))
    # Unreachable while PANEL_CATALOG and this branch agree, but a Panel must
    # never 500 onto a projector.
    return JSONResponse({"ok": True, "state": "no_catalog", "assignments": [],
                         "message": "This panel has no data source yet."})
