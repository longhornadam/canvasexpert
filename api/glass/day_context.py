"""One query for everything a classroom screen shows on a given day.

Before this module each kind of fact had its own mechanism, or none. The bell
schedule came from `api/schedule/`, the district calendar from settings, and
games, dances, tutorials and club hours had nowhere to live at all -- so the
only way to put "Picture day" on a projector was to author a whole dated scene
with the words typed into a pane. Every new kind of announcement wanted a new
mechanism.

So this is the merge point: three sources in, one audience-filtered projection
out, and the fourth source is a function plus a vocabulary entry rather than a
new mechanism.

Two boundaries worth stating, because they are the reason this file is here and
not somewhere tidier:

* **It lives under `api/glass/` because Glass is the only consumer.** If a
  second surface ever wants a day context, move it to `api/` then, not now.
* **It may reach configuration; `api/schedule/` may not.** The schedule package
  stays pure so it is importable without a credential store, which is why the
  bell schedule cannot merge itself with the calendar and why that join happens
  here. Time-of-day *structure* and date-keyed *content* are different things
  that meet on a date.

Every item is tagged from `api/audience.py` and filtered before it leaves, so a
source cannot promote its own fact onto a wall. The tag is stripped from the
projection: once the list is filtered, every survivor is classroom-facing by
construction and the field would be redundant on the wire.

Nothing here raises. A missing schedule, an unconfigured calendar, or a
malformed events file each mean "less to show", never a blank screen.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from api import audience
from api.webui.school_events import DEFAULT_LOOKAHEAD_DAYS

MAX_LOOKAHEAD_DAYS = 31


def day_context(at: datetime | date, *, lookahead_days: int = DEFAULT_LOOKAHEAD_DAYS,
                override: str | None = None, root=None) -> dict:
    """Everything a screen needs for the day `at` falls on.

    `at` may be a date or a datetime. A bare date is treated as midnight, which
    resolves the day's shape without claiming a current block -- the caller that
    wants "what is happening right now" has a clock and passes it in.
    """
    instant = at if isinstance(at, datetime) else datetime.combine(at, time.min)
    day = instant.date()
    span = max(0, min(int(lookahead_days), MAX_LOOKAHEAD_DAYS))
    horizon = day + timedelta(days=span)

    calendar = _calendar(day, horizon)
    no_school = _no_school_dates(calendar.get("no_count_dates"))
    day_type, blocks, current = _schedule(instant, no_school, override=override)

    events = sorted(
        audience.classroom_only(
            _district_events(calendar.get("events")) + _school_events(day, horizon, root)
        ),
        key=_merged_sort_key,
    )

    return {
        "date": day.isoformat(),
        "day_type": day_type,
        "blocks": blocks,
        "current_block": current,
        "events": [_untagged(event) for event in events],
        "grading_periods": _grading_periods(calendar.get("grading_periods")),
        "no_school_dates": sorted(value.isoformat() for value in no_school),
        "lookahead_days": span,
    }


# ------------------------------------------------------------------ source 1


def _schedule(instant: datetime, no_school: frozenset[date], *, override: str | None):
    """Day type, the day's blocks, and the block containing `instant`.

    Imported inside the function so a caller that only wants calendar facts does
    not pay for schedule discovery, and so an unreadable schedule file cannot
    stop the rest of the context from being built.
    """
    try:
        from api.schedule import loader, resolver
    except Exception:
        return (None, [], None)

    try:
        schedule, _notes = loader.discover_bell_schedule()
    except Exception:
        return (None, [], None)
    if not schedule:
        return (None, [], None)

    try:
        resolved = resolver.resolve(schedule, instant, no_school_dates=no_school,
                                    override=override)
    except Exception:
        return (None, [], None)

    if not resolved.day_type:
        return (None, [], None)

    blocks = [{"id": block.block_id, "label": block.label,
               "start": block.start.isoformat(timespec="minutes"),
               "end": block.end.isoformat(timespec="minutes")}
              for block in resolved.day_type.blocks]
    active = resolved.block.block_id if resolved.block else None
    current = next((block for block in blocks if block["id"] == active), None)
    return (resolved.day_type.day_type_id, blocks, current)


# ------------------------------------------------------------------ source 2


def _calendar(day: date, horizon: date) -> dict:
    """The district calendar payload for the window, or an empty one.

    Imported inside the function for the reason `api/schedule/calendar.py`
    documents: this package reaches the credential store through
    `config/_io.py`, and a bare import context has none.
    """
    try:
        from api.webui import config
    except Exception:
        return {}
    try:
        # Positional, matching the seam the existing tests monkeypatch. Keywords
        # here silently turn a signature mismatch into an empty calendar.
        payload = config.get_combined_calendar_for_range(day.isoformat(), horizon.isoformat())
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _no_school_dates(raw: object) -> frozenset[date]:
    """Non-instructional dates, dropping anything unparseable.

    One bad row must not take the range with it: a screen that thinks Saturday
    is a school day is a worse failure than a screen missing one holiday.
    """
    if not isinstance(raw, (list, tuple, set, frozenset)):
        return frozenset()
    found = set()
    for value in raw:
        if isinstance(value, str):
            try:
                found.add(date.fromisoformat(value.strip()))
            except ValueError:
                continue
    return frozenset(found)


def _district_events(raw: object) -> list[dict]:
    """District calendar events, tagged with their audience."""
    if not isinstance(raw, (list, tuple)):
        return []
    return [audience.tag(event) for event in raw if isinstance(event, dict)]


def _grading_periods(raw: object) -> list[dict]:
    if not isinstance(raw, (list, tuple)):
        return []
    return [period for period in raw if isinstance(period, dict)]


# ------------------------------------------------------------------ source 3


def _school_events(day: date, horizon: date, root) -> list[dict]:
    """Teacher-recorded school events in the window, tagged.

    Sorted here rather than merged into the district sort key: a recurring event
    has no single date, and `_event_sort_key` in `config/calendars.py` compares
    that against a date string and raises. The two event streams stay
    distinguishable by kind and are ordered by this module.
    """
    try:
        from api.webui import school_events
    except Exception:
        return []
    try:
        found = school_events.events_for_range(day, horizon, root=root)
    except Exception:
        return []
    return [audience.tag(event) for event in found]


def _untagged(event: dict) -> dict:
    return {key: value for key, value in event.items() if key != "audience"}


# -------------------------------------------------------------------- merging


def _merged_sort_key(event: dict) -> tuple:
    """One order across both event streams.

    The two sources disagree about which field carries the date -- a district
    report card has `report_issue_date`, a no-school span has `start`, and a
    recurring tutorial has no date at all -- so neither source's own key can
    order the merged list. Dated items come first in date order; recurring ones
    trail them, since "Tuesdays and Thursdays" has no place in a date sequence.
    """
    when = (event.get("start") or event.get("end")
            or event.get("report_issue_date") or "")
    first_weekday = (event.get("weekdays") or [7])[0]
    return (0 if when else 1, when, first_weekday,
            event.get("from", ""), event.get("kind", ""), event.get("label", ""))
