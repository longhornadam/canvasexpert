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
from api.webui import deps, school_calendar

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
        data = _district_calendar_events_feed(date_str, span, root)
    elif name == "school_events":
        data = _school_events_feed(date_str, span, root)
    else:
        data = None  # unreachable given FEED_CATALOG's own keys, but never raise

    return {"ok": True, "available": True, "feed": name, "data": data}


def _bell_schedule_feed(date_str: str) -> dict:
    """{"day_type": schedule_id or None, "blocks": [...], "current_block": dict or None}.

    day_type comes from the canonical calendar's resolution for this date, so
    it remains available even when no teacher block meets on that date.
    current_block is only ever populated when date_str is today (a past/future
    date has no meaningful "right now") -- compare against the real local
    clock via datetime.now().strftime("%H:%M") against each block's start/end
    strings."""
    try:
        blocks = deps.resolve_schedule_for(date_str)["blocks"]
    except Exception:
        blocks = []
    try:
        bell_schedules, _problems = deps.load_bell_schedules()
        doc, _cal_problems = school_calendar.read()
        resolution = school_calendar.resolve_date(doc, date_str, bell_schedules)
        day_type = resolution.get("schedule_id")
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


def _district_calendar_events_feed(date_str: str, lookahead_days: int, root=None) -> list[dict]:
    """Academic-calendar facts synthesized from the canonical document:
    no-school/no-regular-classes days and grading-period end/report-card
    dates. These are structural fields in School Calendar.json now (a day
    kind, a grading_periods entry), not a stored events list, so this feed
    reconstructs the same event shape SmartDeck slides already expect."""
    try:
        day = date_type.fromisoformat(date_str)
        horizon = day + timedelta(days=lookahead_days)
        projection, _problems = school_calendar.range_projection(
            day.isoformat(), horizon.isoformat(), root=root)
        raw = _synthesize_academic_events(projection) if projection else []
    except Exception:
        raw = []
    events = [audience.tag(e) for e in raw]
    safe = audience.classroom_only(events)
    return [_untagged(e) for e in safe]


def _synthesize_academic_events(projection: dict) -> list[dict]:
    events = []
    for day_key, entry in projection.get("days", {}).items():
        if entry.get("kind") in ("no_school", "no_regular_classes") and entry.get("label"):
            events.append({"kind": "no_school", "label": entry["label"],
                           "start": day_key, "end": day_key})
    for period in projection.get("grading_periods", []):
        label = period.get("name") or period.get("code") or ""
        events.append({"kind": "grading_period_end", "label": label,
                       "code": period.get("code", ""), "end": period["end"]})
        if period.get("report_issue_date"):
            events.append({"kind": "report_card", "label": label,
                           "code": period.get("code", ""),
                           "report_issue_date": period["report_issue_date"]})
    return sorted(events, key=_event_sort_key)


def _school_events_feed(date_str: str, lookahead_days: int, root) -> list[dict]:
    """Teacher-recorded public school events from the canonical calendar's
    events array, tagged, filtered, and stripped for classroom display."""
    try:
        day = date_type.fromisoformat(date_str)
        horizon = day + timedelta(days=lookahead_days)
        projection, _problems = school_calendar.range_projection(
            day.isoformat(), horizon.isoformat(), root=root)
        found = projection.get("events", []) if projection else []
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
