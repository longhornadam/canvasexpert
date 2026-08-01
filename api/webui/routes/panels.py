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

DEFAULT_THEME = "ce"

# Themes are a skin, not a layout: each one is a set of custom properties in
# static/panels/themes.css, so a theme can never change what a panel shows or
# how many rows fit. Ordered for the console's dropdown.
PANEL_THEMES = (
    ("ce", "Canvas Expert"),
    ("natural", "Natural"),
    ("ocean", "Ocean"),
    ("cottage", "Cottage"),
    ("console", "Console"),
    ("wizardtrain", "Wizard train"),
    ("bauhaus", "Bauhaus"),
    ("lisa", "Lisa"),
)
_THEME_KEYS = frozenset(key for key, _label in PANEL_THEMES)


def resolve_theme(value) -> str:
    """A known theme key, or the default.

    Never rejects. A theme retired between releases, or a hand-edited one,
    would otherwise take a saved board down weeks later over a decoration.
    """
    key = str(value or "").strip().lower()
    return key if key in _THEME_KEYS else DEFAULT_THEME


# deck_schedule.resolve_day emits this when the day calendar has no entry for
# a date, which is how a weekend or holiday is told apart from a teacher who
# never set a schedule up at all. test_no_school_day_marker_still_matches
# pins it, so a reword there fails a test instead of silently turning every
# summer day into "set up your schedule".
_NO_SCHOOL_DAY_MARKER = "no schedule for"


def resolve_panel_course(course: str, *, now=None, schedule_reader=None) -> dict:
    """Which course a Panel should show right now.

    An explicit ``course`` pins the panel to one section. Otherwise it follows
    the teacher's own schedule, which the app already resolves for SmartDeck:
    the block meeting now, or the next one today. A pinned course id dies at
    the year rollover and takes a saved board quietly with it; a schedule does
    not, because the teacher updates it once and every board follows.

    Returns ``course_id`` plus a ``relation`` of pinned/now/next, or a named
    ``state`` when no course applies. Never raises: this runs for a page on a
    classroom wall.
    """
    if course:
        return {"course_id": str(course), "relation": "pinned",
                "block": "", "state": "", "message": "", "next_change": ""}

    now = now or datetime.now()
    reader = schedule_reader or deps.resolve_schedule_for
    try:
        blocks, problems = reader(now.date().isoformat())
    except Exception:
        blocks, problems = [], []

    if not blocks:
        if any(_NO_SCHOOL_DAY_MARKER in str(p) for p in problems):
            return _no_course("not_school_day", "No classes scheduled today.")
        return _no_course(
            "no_schedule",
            "Set your class schedule in Canvas Expert and this follows your day.")

    now_hhmm = now.strftime("%H:%M")
    block = next((b for b in blocks if b["start"] <= now_hhmm < b["end"]), None)
    relation = "now"
    if block is None:
        # resolve_day sorts by start, so the first block still ahead is next.
        block = next((b for b in blocks if b["start"] > now_hhmm), None)
        relation = "next"
    if block is None:
        return _no_course("day_over", "No more classes today.")

    name = str(block.get("label") or block.get("name") or "")
    course_id = str(block.get("course_id") or "")
    if not course_id:
        # Conference, duty, advisory: a real block with no Canvas course.
        # Name it rather than reporting an error nobody can act on mid-class.
        return _no_course("block_without_course",
                          f"No Canvas course linked to {name}." if name
                          else "No Canvas course linked to this block.",
                          block=name)

    return {
        "course_id": course_id,
        "relation": relation,
        "block": name,
        "state": "",
        "message": "",
        # When this panel stops being right. The panel re-reads at the bell
        # instead of drifting for up to a refresh interval into the next class.
        "next_change": str(block["end"] if relation == "now" else block["start"]),
    }


def _no_course(state: str, message: str, block: str = "") -> dict:
    return {"course_id": "", "relation": "", "block": block,
            "state": state, "message": message, "next_change": ""}


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
        "nav_section": "panels",
        "panels": panels,
        "courses": courses,
        "default_days": DEFAULT_LOOKAHEAD_DAYS,
        "max_days": MAX_LOOKAHEAD_DAYS,
        "themes": [{"key": key, "label": label} for key, label in PANEL_THEMES],
        "default_theme": DEFAULT_THEME,
    })


@router.get("/panels/{kind}", response_class=HTMLResponse)
def panel_page(request: Request, kind: str, theme: str = DEFAULT_THEME):
    """One Panel, chrome-free, sized to whatever box it is dropped into."""
    spec = PANEL_CATALOG.get(kind)
    if spec is None:
        return HTMLResponse(f"Unknown panel: {kind}", status_code=404)
    return deps.templates.TemplateResponse(request, spec["template"], {
        "kind": kind,
        "panel_title": spec["title"],
        "theme": resolve_theme(theme),
    })


@router.get("/panels/{kind}/data")
def panel_data(kind: str, course: str = "", days: int = DEFAULT_LOOKAHEAD_DAYS):
    """The Panel's single data fetch. Disk-only; never calls Canvas."""
    if kind not in PANEL_CATALOG:
        return JSONResponse({"ok": False, "error": f"Unknown panel: {kind}"},
                            status_code=404)
    if kind == "whats-due":
        scope = resolve_panel_course(course)
        if scope["state"]:
            return JSONResponse({
                "ok": True, "state": scope["state"], "days": days,
                "assignments": [], "message": scope["message"],
                "relation": "", "block": scope["block"], "next_change": "",
            })
        payload = whats_due_payload(scope["course_id"], days)
        payload["relation"] = scope["relation"]
        payload["block"] = scope["block"]
        payload["next_change"] = scope["next_change"]
        if not payload.get("course_name"):
            payload["course_name"] = scope["block"]
        return JSONResponse(payload)
    # Unreachable while PANEL_CATALOG and this branch agree, but a Panel must
    # never 500 onto a projector.
    return JSONResponse({"ok": True, "state": "no_catalog", "assignments": [],
                         "message": "This panel has no data source yet."})
