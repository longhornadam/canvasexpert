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
from api.webui import config, deps, school_calendar

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


# Calendar resolution states that mean "the calendar itself needs a teacher
# repair" versus "this is legitimately not a school day" -- kept distinct so a
# summer weekend never nags for setup and a broken calendar never reads as a
# quiet day off. See docs/contracts/canonical-school-calendar-contract.md §4.
_CALENDAR_REPAIR_STATES = {"unconfigured", "invalid_calendar", "outside_coverage", "unknown_schedule"}
_CALENDAR_NO_SCHOOL_STATES = {"no_school", "no_regular_classes"}
_CALENDAR_REPAIR_MESSAGE = "Calendar needs attention. Open Calendar in Canvas Expert."


def _resolve_calendar_state(date_str: str) -> str:
    """The canonical calendar's resolution state for one date, or "ready" on
    any internal failure -- the schedule_reader's own result decides in that
    case, so this never independently takes the panel down."""
    try:
        bell_schedules, _problems = deps.load_bell_schedules()
        doc, _problems = school_calendar.read()
        return school_calendar.resolve_date(doc, date_str, bell_schedules)["state"]
    except Exception:
        return "ready"


def _course_for_block(block: dict, *, relation: str, next_change: str,
                      active_courses_reader) -> dict:
    """Turn a resolved Teacher Schedule block into a Panel course result,
    enforcing the Current-course boundary: a block mapped to a Previous (or
    unknown) course never reads its catalog."""
    name = str((block or {}).get("label") or (block or {}).get("name") or "")
    course_id = str((block or {}).get("course_id") or "")
    if not course_id:
        # Conference, duty, advisory: a real block with no Canvas course.
        # Name it rather than reporting an error nobody can act on mid-class.
        return _no_course("block_without_course",
                          f"No Canvas course linked to {name}." if name
                          else "No Canvas course linked to this block.",
                          block=name)
    try:
        active_ids = {str(c.get("id")) for c in (active_courses_reader() or [])}
    except Exception:
        active_ids = set()
    if course_id not in active_ids:
        return _no_course("previous_course",
                          "This class is no longer current. Update its Canvas course in Calendar.",
                          block=name)
    return {
        "course_id": course_id,
        "relation": relation,
        "block": name,
        "state": "",
        "message": "",
        # When this panel stops being right. The panel re-reads at the bell
        # instead of drifting for up to a refresh interval into the next class.
        "next_change": next_change,
    }


def resolve_panel_course(block: str, *, now=None, schedule_reader=None,
                         teacher_schedule_reader=None, active_courses_reader=None,
                         calendar_state=None) -> dict:
    """Which course a Panel should show right now.

    A stable ``?block=<teacher-block-name>`` pins the panel to that Teacher
    Schedule block: it still resolves through the Teacher Schedule and still
    enforces the Current-course boundary, but bypasses date/clock resolution
    -- the contract's one intentional override (raw ``?course=`` pinning is
    retired: a pinned course id died at the year rollover and took a saved
    board quietly with it, where a stable block name does not). Otherwise the
    panel follows the live calendar/clock: the block meeting now, or the next
    one today.

    Returns ``course_id`` plus a ``relation`` of pinned/now/next, or a named
    ``state`` when no course applies. Never raises: this runs for a page on a
    classroom wall.
    """
    active_reader = active_courses_reader or config.active_courses
    teacher_reader = teacher_schedule_reader or deps.load_teacher_schedule
    try:
        teacher_schedule, _problems = teacher_reader()
    except Exception:
        teacher_schedule = {}
    teacher_blocks = teacher_schedule.get("blocks") if isinstance(teacher_schedule, dict) else []
    if not isinstance(teacher_blocks, list):
        teacher_blocks = []

    if block:
        matched = next(
            (b for b in teacher_blocks
             if isinstance(b, dict) and str(b.get("name") or "") == block),
            None)
        if matched is None:
            return _no_course("no_schedule",
                              "This block is not in your Teacher Schedule.", block=block)
        return _course_for_block(matched, relation="pinned", next_change="",
                                 active_courses_reader=active_reader)

    now = now or datetime.now()
    date_str = now.date().isoformat()

    state = _resolve_calendar_state(date_str) if calendar_state is None else calendar_state
    if state in _CALENDAR_REPAIR_STATES:
        return _no_course("calendar_needs_attention", _CALENDAR_REPAIR_MESSAGE)
    if state in _CALENDAR_NO_SCHOOL_STATES:
        return _no_course("not_school_day", "No classes scheduled today.")

    reader = schedule_reader or deps.resolve_schedule_for
    try:
        blocks, _problems = reader(date_str)
    except Exception:
        blocks = []

    if not blocks:
        return _no_course(
            "no_schedule",
            "Set your class schedule in Canvas Expert and this follows your day.")

    now_hhmm = now.strftime("%H:%M")
    active_block = next((b for b in blocks if b["start"] <= now_hhmm < b["end"]), None)
    relation = "now"
    if active_block is None:
        # resolve_day sorts by start, so the first block still ahead is next.
        active_block = next((b for b in blocks if b["start"] > now_hhmm), None)
        relation = "next"
    if active_block is None:
        return _no_course("day_over", "No more classes today.")

    next_change = str(active_block["end"] if relation == "now" else active_block["start"])
    return _course_for_block(active_block, relation=relation, next_change=next_change,
                             active_courses_reader=active_reader)


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
    """Published assignments due through ``today + days`` (local calendar
    days), future items first then earlier-today items, each bucket
    chronological.

    Always ``ok``: a Panel on a wall has no way to report an exception, so
    every outcome is a named ``state`` the template can render calmly.
    An earlier-today item stays visible all day rather than disappearing the
    moment its due time passes -- it is described neutrally, never as missing
    or late. ``now`` and ``catalog_reader`` are injected by tests.
    """
    now = now or datetime.now(timezone.utc)
    local_now = now.astimezone()
    today = local_now.date()
    days = max(1, min(int(days), MAX_LOOKAHEAD_DAYS))
    horizon_date = today + timedelta(days=days)

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

    items = []
    for record in scope.get("records") or []:
        if not isinstance(record, dict):
            continue
        if not record.get("published", True):
            continue
        due = _parse_due(record.get("due_at"))
        if due is None:
            continue
        due_date = due.astimezone().date()
        if due_date < today or due_date > horizon_date:
            continue
        items.append({
            "title": str(record.get("name") or "Untitled assignment"),
            "due_at": due.isoformat(),
            "points": record.get("points_possible"),
            "_earlier_today": due_date == today and due < now,
        })
    # Future/upcoming items first, then earlier-today items; each bucket
    # chronological so ties stay deterministic.
    items.sort(key=lambda item: (item["_earlier_today"], item["due_at"]))
    for item in items:
        del item["_earlier_today"]

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
    """Console: pick a Panel, optionally fix it to one Teacher Schedule
    block, copy the embed code."""
    courses = [
        {"id": str(c.get("id", "")), "name": str(c.get("name", "")) or f"Course {c.get('id', '')}"}
        for c in (config.active_courses() or [])
    ]
    teacher_schedule, _problems = deps.load_teacher_schedule()
    teacher_blocks = teacher_schedule.get("blocks") if isinstance(teacher_schedule, dict) else []
    blocks = [
        str(b.get("name") or "") for b in (teacher_blocks or [])
        if isinstance(b, dict) and b.get("name")
    ]
    panels = [dict(spec, kind=kind) for kind, spec in sorted(PANEL_CATALOG.items())]
    return deps.templates.TemplateResponse(request, "panels.html", {
        "nav_section": "panels",
        "panels": panels,
        "courses": courses,
        "blocks": blocks,
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
def panel_data(kind: str, block: str = "", days: int = DEFAULT_LOOKAHEAD_DAYS):
    """The Panel's single data fetch. Disk-only; never calls Canvas."""
    if kind not in PANEL_CATALOG:
        return JSONResponse({"ok": False, "error": f"Unknown panel: {kind}"},
                            status_code=404)
    if kind == "whats-due":
        scope = resolve_panel_course(block)
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
