"""The Glass page: one screen that shows a room what is happening now.

Deliberately thin. Reading the bell schedule, reading the day plan, and shaping
the render blob all live behind this file, so the only work here is picking the
instant, gathering the pieces, and handing one structure to the template.

`?at=<ISO8601>` overrides the instant for the whole render and reaches the
browser with ticking suspended. That is the frozen-clock seam: every state of
the day is reachable from a URL, so no test has to wait for 12:13 to come
around and no page has to grow a debug mode.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from api.glass import store, view
from api.schedule import calendar as schedule_calendar
from api.schedule import loader, resolver

from .. import config
from ..deps import templates

router = APIRouter(tags=["glass"])

# How far ahead to ask the academic calendar about, matching the window the
# Bobcat Hour lookup searches so a holiday inside it is honoured.
CALENDAR_LOOKAHEAD_DAYS = 14


@router.get("/glass", response_class=HTMLResponse)
def glass_page(request: Request, at: str = Query("")):
    """The whole day, rendered once, for a projector at the front of a room."""
    instant, frozen = _instant(at)
    schedule, notes = loader.discover_bell_schedule()
    plan, plan_notes = store.load_day_plan(instant.date())
    no_school = schedule_calendar.no_school_dates(
        instant.date(), instant.date() + timedelta(days=CALENDAR_LOOKAHEAD_DAYS)
    )
    blob = view.build_view(
        schedule=schedule,
        plan=plan,
        at=instant,
        no_school_dates=no_school,
        notes=[*notes, *plan_notes],
        next_plan=_next_bobcat_plan(schedule, instant, no_school),
        clock_frozen=frozen,
    )
    return templates.TemplateResponse(request, "glass.html", {
        "nav_section": "glass",
        "token_is_set": config.token_is_set(),
        "glass": blob,
    })


def _instant(raw: str) -> tuple[datetime, bool]:
    """The moment to render, and whether it was pinned by the caller.

    An unparseable value falls back to the real clock rather than failing the
    page, because the page's job is to be on the wall.
    """
    text = (raw or "").strip()
    if text:
        try:
            return datetime.fromisoformat(text), True
        except ValueError:
            pass
    return datetime.now(), False


def _next_bobcat_plan(schedule, instant: datetime, no_school):
    """The plan for the next Bobcat Hour falling on a date after today.

    The pane shows the next Bobcat Hour that has not ended yet, so after lunch
    it is tomorrow's, and its offerings have to come from tomorrow's plan.
    Today's list under tomorrow's heading would be wrong on the wall all
    afternoon. Reading it here is what lets the pane flip itself when the block
    ends without the page asking the server anything.
    """
    if schedule is None:
        return None
    tomorrow = datetime.combine(instant.date(), time.min) + timedelta(days=1)
    try:
        occurrence = resolver.next_occurrence(
            schedule,
            tomorrow,
            view.BOBCAT_HOUR_KIND,
            no_school_dates=no_school,
            search_days=view.BOBCAT_SEARCH_DAYS,
        )
    except ValueError:
        return None
    if occurrence is None:
        return None
    return store.load_day_plan(occurrence.on)[0]
