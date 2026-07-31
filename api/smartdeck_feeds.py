"""Feed resolution for SmartDeck.

Moved from api/glass/day_context.py (Glass is deleted, day_context.py's only
consumer). The merge/audience-tag/strip pipeline is preserved unchanged; the
bell-schedule source is redirected from the old, now-dead api.schedule.loader/
resolver system onto api.webui.deps.resolve_schedule_for (built for SmartDeck
in an earlier slice).

Feeds are a closed allowlist: FEED_CATALOG is the single source of truth for
every recognized feed name. A name absent from this dict cannot resolve to
anything -- resolve_feed() raises ValueError for it, never a best-effort guess.
This is deliberate: "unreachable by construction," not merely unimplemented.

Per-student feeds (birthdays_today, missing_assignments, positive_achievements,
staar_masters) are named here -- so an unrecognized-name check still rejects
typos the same way -- but have no producer yet (that's a separate, unstarted
Canvas Mirror/roster body of work). resolve_feed() returns a graceful
not-yet-available result for these, never a crash or a fabricated value.

Nothing here raises for a RECOGNIZED feed name -- a missing schedule, an
unconfigured calendar, or a malformed events file each mean "less to show,"
never an exception. Only an unrecognized name raises.
"""
from __future__ import annotations

from datetime import date as date_type, datetime, timedelta

from api import audience
from api.webui import deps, school_events, config

DEFAULT_LOOKAHEAD_DAYS = 14
MAX_LOOKAHEAD_DAYS = 31

FEED_CATALOG = {
    "bell_schedule": "available",
    "district_calendar_events": "available",
    "school_events": "available",
    "birthdays_today": "not_yet_available",
    "missing_assignments": "not_yet_available",
    "positive_achievements": "not_yet_available",
    "staar_masters": "not_yet_available",
}


def list_feed_names() -> list[str]:
    """Every recognized feed name, sorted."""
    return sorted(FEED_CATALOG)


def resolve_feed(name: str, date_str: str, *, lookahead_days: int = DEFAULT_LOOKAHEAD_DAYS,
                  root=None) -> dict:
    """Resolve one feed by name for one date (YYYY-MM-DD).

    Raises ValueError for a name not in FEED_CATALOG at all -- that's the
    allowlist-rejection behavior, and it must be unreachable by construction,
    not a soft error. For any recognized name, never raises; internal
    failures degrade to less data, matching day_context.py's original
    "nothing here raises" contract for its own three sources.
    """
    if name not in FEED_CATALOG:
        raise ValueError(f"unknown feed: {name!r}; expected one of {sorted(FEED_CATALOG)}")

    if FEED_CATALOG[name] == "not_yet_available":
        return {"ok": True, "available": False, "feed": name, "reason": "not yet available"}

    span = max(0, min(int(lookahead_days), MAX_LOOKAHEAD_DAYS))

    if name == "bell_schedule":
        data = _bell_schedule_feed(date_str)
    elif name == "district_calendar_events":
        data = _district_calendar_events_feed(date_str, span)
    elif name == "school_events":
        data = _school_events_feed(date_str, span, root)
    else:
        data = None  # unreachable given FEED_CATALOG's own keys, but never raise

    return {"ok": True, "available": True, "feed": name, "data": data}


def _bell_schedule_feed(date_str: str) -> dict:
    """{"day_type": schedule_id or None, "blocks": [...], "current_block": dict or None}.

    day_type comes directly from the day calendar, so it remains available even
    when no teacher block meets on that date. current_block
    is only ever populated when date_str is today (a past/future date has no
    meaningful "right now") -- compare against the real local clock via
    datetime.now().strftime("%H:%M") against each block's start/end strings."""
    try:
        blocks, _problems = deps.resolve_schedule_for(date_str)
    except Exception:
        blocks = []
    try:
        day_calendar, _problems = deps.load_day_calendar()
        day_type = day_calendar.get(date_str)
    except Exception:
        day_type = None
    current_block = None
    try:
        if date_str == date_type.today().isoformat():
            now_hhmm = datetime.now().strftime("%H:%M")
            current_block = next(
                (b for b in blocks if b["start"] <= now_hhmm < b["end"]), None)
    except Exception:
        current_block = None
    return {"day_type": day_type, "blocks": blocks, "current_block": current_block}


def _district_calendar_events_feed(date_str: str, lookahead_days: int) -> list[dict]:
    """District calendar events (config.get_combined_calendar_for_range), tagged
    via audience.tag, filtered via audience.classroom_only, tag stripped before
    returning -- exactly day_context.py's original _district_events pipeline,
    just scoped to this one feed instead of merged with school events."""
    try:
        day = date_type.fromisoformat(date_str)
        horizon = day + timedelta(days=lookahead_days)
        payload = config.get_combined_calendar_for_range(day.isoformat(), horizon.isoformat())
        raw = payload.get("events") if isinstance(payload, dict) else None
    except Exception:
        raw = None
    events = [audience.tag(e) for e in raw] if isinstance(raw, (list, tuple)) else []
    safe = audience.classroom_only(events)
    return [_untagged(e) for e in safe]


def _school_events_feed(date_str: str, lookahead_days: int, root) -> list[dict]:
    """Teacher-recorded school events (api.webui.school_events.events_for_range),
    tagged, filtered, stripped -- same pipeline, this module's own event stream
    (not merged with district events -- they're two separate feeds per the
    brief's own naming, sourced from two different modules)."""
    try:
        day = date_type.fromisoformat(date_str)
        horizon = day + timedelta(days=lookahead_days)
        found = school_events.events_for_range(day, horizon, root=root)
    except Exception:
        found = []
    events = [audience.tag(e) for e in found] if isinstance(found, list) else []
    safe = audience.classroom_only(events)
    return [_untagged(e) for e in sorted(safe, key=_event_sort_key)]


def _untagged(event: dict) -> dict:
    return {key: value for key, value in event.items() if key != "audience"}


def _event_sort_key(event: dict) -> tuple:
    """Dated items first in date order, then recurring ones (no single date) --
    reused from day_context.py's _merged_sort_key, scoped to one event stream
    now instead of two merged ones."""
    when = event.get("start") or event.get("end") or event.get("report_issue_date") or ""
    first_weekday = (event.get("weekdays") or [7])[0]
    return (0 if when else 1, when, first_weekday,
            event.get("from", ""), event.get("kind", ""), event.get("label", ""))
