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

import os
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from api import panel_themes
from api.webui import (config, deps, panel_data as panel_data_service,
                       school_calendar, workspace)

router = APIRouter()

DEFAULT_LOOKAHEAD_DAYS = panel_data_service.DEFAULT_DUE_DAYS
MAX_LOOKAHEAD_DAYS = panel_data_service.MAX_DUE_DAYS

PANEL_CATALOG = {
    "whats-due": {
        "title": "What's due",
        "blurb": "Upcoming assignment due dates for one course. No student data.",
        "template": "panel_whats_due.html",
        "needs_course": True,
        "days": True,
        "default_days": panel_data_service.DEFAULT_DUE_DAYS,
        "max_days": panel_data_service.MAX_DUE_DAYS,
    },
    "random-student": {
        "title": "Random student",
        "blurb": "Choose a current student from the local roster.",
        "template": "panel_random_student.html",
        "needs_course": True,
        "interactive": True,
    },
    "random-student-no-repeats": {
        "title": "Random student (no repeats)",
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
    "learning-objective": {
        "title": "Learning objective",
        "blurb": "Today's reviewed objective from the current course.",
        "template": "panel_learning_objective.html",
        "needs_course": True,
    },
}

DEFAULT_THEME = "ce"

# Themes are a skin, not a layout: each one is a set of custom properties, so a
# theme can never change what a panel shows or how many rows fit. Built-ins are
# hand-written blocks in static/panels/themes.css and their keys are the list in
# api/panel_themes.py, which the MCP tools read too. The teacher's own themes
# are JSON files in the synced Library, generated into CSS at request time by
# /panels/themes.css. Built-in order here is the console's dropdown order.
PANEL_THEMES = panel_themes.BUILTIN_THEMES
_THEME_KEYS = panel_themes.BUILTIN_KEYS


def custom_themes() -> dict:
    """The teacher's own themes from the synced workspace, plus any problems.

    Read fresh on each call rather than cached: a teacher who just asked their
    assistant for a theme expects it in the dropdown on the next load, and the
    cost is a listdir over at most a couple of dozen small files.
    """
    return panel_themes.load_custom_themes()


def resolve_theme(value) -> str:
    """A known theme key, built-in or the teacher's own, or the default.

    Never rejects. A theme retired between releases, deleted from the
    workspace, or hand-edited into something unparseable would otherwise take
    a saved board down weeks later over a decoration.
    """
    key = str(value or "").strip().lower()
    if key in _THEME_KEYS:
        return key
    if key and any(theme["key"] == key for theme in custom_themes()["themes"]):
        return key
    return DEFAULT_THEME


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
    mine = custom_themes()
    art = panel_themes.list_theme_art()
    # Per-entry placement diagnostics (tiny watermark, JPG rectangle, missing
    # file) come from derive(); surface them beside the art list.
    art_diagnostics = []
    for theme in mine["themes"]:
        derived = panel_themes.derive(theme)
        art_diagnostics.extend(derived.get("art_diagnostics") or [])
    return deps.templates.TemplateResponse(request, "panels.html", {
        "nav_section": "panels",
        "panels": panels,
        "courses": courses,
        "blocks": blocks,
        "themes": [{"key": key, "label": label} for key, label in PANEL_THEMES],
        "custom_themes": [{"key": theme["key"], "label": theme["label"]}
                          for theme in mine["themes"]],
        "theme_problems": mine["problems"],
        "art_files": art["files"],
        "art_problems": art["problems"],
        "art_diagnostics": art_diagnostics,
        "themes_dir": workspace.panel_themes_dir() or "",
        "default_theme": DEFAULT_THEME,
    })


@router.get("/panels/themes.css")
def panel_custom_themes_css(theme: str = ""):
    """The teacher's own themes as CSS, generated from their theme files.

    Registered ahead of ``/panels/{kind}`` because that route is a catch-all:
    below it, this path would resolve as a Panel kind and 404.

    Every Panel links this after the built-in stylesheet. It is generated from
    parsed values, never from file text, so nothing a theme file contains can
    become a selector or a property name here. Sent no-store so a theme edit
    lands on the next load of a board that has been open all period.

    ``?theme=<key>`` scopes the response to one theme's block, which is what a
    Panel links so a board with nine panels does not re-download every theme.
    Absent the parameter, all themes are returned so nothing existing breaks.
    """
    themes = custom_themes()["themes"]
    key = str(theme or "").strip().lower()
    if key:
        themes = [entry for entry in themes if entry["key"] == key]
    css = panel_themes.custom_css(themes)
    return Response(css, media_type="text/css",
                    headers={"Cache-Control": "no-store"})


@router.get("/panels/theme-art/{key}/{index}.{ext}")
def panel_theme_art(key: str, index: int, ext: str):
    """The processed bytes for one art entry, cached and immutable.

    Registered next to ``/panels/themes.css`` so the ordering rule (these
    specific routes before the ``/panels/{kind}`` catch-all) stays in one
    place. The generated CSS references this with a content hash, so the
    response is safe to cache forever: a change to the source or the entry
    changes the hash and therefore the URL.
    """
    if ("." + ext) not in panel_themes.ART_EXTENSIONS:
        return Response("not found", status_code=404)
    theme = next((entry for entry in custom_themes()["themes"]
                  if entry["key"] == key), None)
    if theme is None:
        return Response("not found", status_code=404)
    entries = theme.get("art") or []
    if index < 0 or index >= len(entries):
        return Response("not found", status_code=404)
    entry = entries[index]
    source = panel_themes._art_source_path(entry["file"])
    if not source or not os.path.isfile(workspace.extended_path(source)):
        return Response("not found", status_code=404)
    derived = panel_themes.derive(theme)
    derived_colors = {
        "bg": derived["variables"]["--bg"],
        "ink": derived["variables"]["--ink"],
        "accent": derived["variables"]["--accent"],
        "highlight": derived["variables"]["--today-accent"],
    }
    data, out_ext, _diagnostic = panel_themes._process_art(
        source, entry, derived_colors)
    if not data:
        return Response("not found", status_code=404)
    media = {
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(out_ext, "application/octet-stream")
    return Response(data, media_type=media,
                    headers={"Cache-Control": "public, max-age=31536000, immutable"})


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
    if kind == "learning-objective":
        scope = resolve_panel_course(block)
        if scope["state"]:
            return JSONResponse({
                "ok": True, "state": scope["state"], "objective": "",
                "message": scope["message"], "block": scope["block"],
                "relation": "", "next_change": "",
            })
        payload = panel_data_service.learning_objective_payload(scope["course_id"])
        payload["relation"] = scope["relation"]
        payload["block"] = scope["block"]
        payload["next_change"] = scope["next_change"]
        if not payload.get("course_name"):
            payload["course_name"] = scope["block"]
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
