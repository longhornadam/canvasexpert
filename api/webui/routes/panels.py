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
  ``http://127.0.0.1:8765/panels/whats-due?block=ELA-7-B`` into a board they
  save, and that string has to still work after restarts and upgrades. Do not
  add "helpfully pick a free port" fallback to the launcher, and do not move
  Panels onto generated ids: both silently kill every saved board weeks later.

Panel kinds live in PANEL_CATALOG, which is an allowlist. Unknown kinds 404
rather than rendering something improvised, for the same reason SmartDeck has
three fixed layouts: a closed set is what keeps this from sprawling.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from api.webui import config, deps, panel_data as panel_data_service, school_calendar

router = APIRouter()

DEFAULT_LOOKAHEAD_DAYS = panel_data_service.DEFAULT_DUE_DAYS
MAX_LOOKAHEAD_DAYS = panel_data_service.MAX_DUE_DAYS

PANEL_CATALOG = {
    "whats-due": {
        "title": "What's due",
        "blurb": "Upcoming assignment due dates for one course. No student data.",
        "template": "panel_whats_due.html",
        "needs_course": True,
    },
    "random-student": {
        "title": "Random student",
        "blurb": "Choose a current student from the local roster.",
        "template": "panel_random_student.html",
        "needs_course": True,
        "interactive": True,
    },
    "random-student-no-repeats": {
        "title": "Random student — no repeats",
        "blurb": "Choose each current student once, then reset the cycle.",
        "template": "panel_random_student_no_repeats.html",
        "needs_course": True,
        "interactive": True,
    },
    "upcoming-events": {
        "title": "Upcoming events",
        "blurb": "Public Calendar events and academic dates for the classroom.",
        "template": "panel_upcoming_events.html",
        "needs_course": False,
        "days": True,
        "default_days": panel_data_service.DEFAULT_UPCOMING_DAYS,
        "max_days": panel_data_service.MAX_UPCOMING_DAYS,
    },
    "sports-results": {
        "title": "Sports results",
        "blurb": "Recent public game results recorded in Calendar.",
        "template": "panel_sports_results.html",
        "needs_course": False,
        "days": True,
        "default_days": panel_data_service.DEFAULT_SPORTS_DAYS,
        "max_days": panel_data_service.MAX_SPORTS_DAYS,
    },
    "bobcat-hour": {
        "title": "Bobcat Hour",
        "blurb": "Today's canonical tutorial and club blocks.",
        "template": "panel_bobcat_hour.html",
        "needs_course": False,
    },
    "missing-work": {
        "title": "Missing work",
        "blurb": "Published work marked missing in the current local roster.",
        "template": "panel_missing_work.html",
        "needs_course": True,
    },
    "birthdays-celebrations": {
        "title": "Birthdays & celebrations",
        "blurb": "Current roster birthdays and teacher-entered celebrations.",
        "template": "panel_birthdays_celebrations.html",
        "needs_course": True,
        "days": True,
        "default_days": panel_data_service.DEFAULT_BIRTHDAY_DAYS,
        "max_days": panel_data_service.MAX_BIRTHDAY_DAYS,
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
    enforces the Current-course boundary, but bypasses date/clock resolution.
    Otherwise the
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
        blocks = reader(date_str).get("blocks") or []
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


whats_due_payload = panel_data_service.whats_due_payload


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
def panel_data(kind: str, block: str = "", days: int | None = None):
    """The Panel's single data fetch. Disk-only; never calls Canvas."""
    if kind not in PANEL_CATALOG:
        return JSONResponse({"ok": False, "error": f"Unknown panel: {kind}"},
                            status_code=404)
    if kind == "whats-due":
        requested_days = DEFAULT_LOOKAHEAD_DAYS if days is None else days
        scope = resolve_panel_course(block)
        if scope["state"]:
            return JSONResponse({
                "ok": True, "state": scope["state"], "days": requested_days,
                "assignments": [], "message": scope["message"],
                "relation": "", "block": scope["block"], "next_change": "",
            })
        payload = whats_due_payload(scope["course_id"], requested_days)
        payload["relation"] = scope["relation"]
        payload["block"] = scope["block"]
        payload["next_change"] = scope["next_change"]
        if not payload.get("course_name"):
            payload["course_name"] = scope["block"]
        return JSONResponse(payload)
    if kind in {"random-student", "random-student-no-repeats", "missing-work",
                "birthdays-celebrations"}:
        scope = resolve_panel_course(block)
        if scope["state"]:
            key = "items" if kind == "birthdays-celebrations" else (
                "students" if kind == "missing-work" else "names")
            payload = {"ok": True, "state": scope["state"], key: [],
                       "message": scope["message"], "block": scope["block"]}
            if kind == "birthdays-celebrations":
                payload["days"] = panel_data_service.clamp_days(
                    days if days is not None else panel_data_service.DEFAULT_BIRTHDAY_DAYS,
                    panel_data_service.DEFAULT_BIRTHDAY_DAYS,
                    panel_data_service.MAX_BIRTHDAY_DAYS)
            return JSONResponse(payload)
        if kind == "random-student":
            payload = panel_data_service.random_student_payload(scope["course_id"])
        elif kind == "random-student-no-repeats":
            payload = panel_data_service.random_student_no_repeats_payload(scope["course_id"])
        elif kind == "missing-work":
            payload = panel_data_service.missing_work_payload(scope["course_id"])
        else:
            payload = panel_data_service.birthdays_celebrations_payload(
                scope["course_id"],
                panel_data_service.DEFAULT_BIRTHDAY_DAYS if days is None else days)
        payload["relation"] = scope["relation"]
        payload["block"] = scope["block"]
        payload["next_change"] = scope["next_change"]
        return JSONResponse(payload)
    if kind == "upcoming-events":
        return JSONResponse(panel_data_service.upcoming_events_payload(
            panel_data_service.DEFAULT_UPCOMING_DAYS if days is None else days))
    if kind == "sports-results":
        return JSONResponse(panel_data_service.sports_results_payload(
            panel_data_service.DEFAULT_SPORTS_DAYS if days is None else days))
    if kind == "bobcat-hour":
        return JSONResponse(panel_data_service.bobcat_hour_payload())
    return JSONResponse({"ok": True, "state": "calendar_needs_attention",
                         "events": [], "message": "This panel needs attention."})
