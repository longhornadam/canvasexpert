"""Academic calendars — district no-count dates for sweep / extensions.

Uses lazy module-reference so monkeypatches to config._io propagate correctly.
"""
from datetime import date

from . import _io as _io_mod


def _normalized_date(value) -> str | None:
    """Return an exact public ISO date, or reject an untrusted value."""
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed.isoformat() if value == parsed.isoformat() else None


def _normalize_event(event) -> dict | None:
    """Keep only the small, public calendar-event projection.

    Calendar settings can predate events or be hand-edited.  Never let a
    malformed stored record raise here or carry an implementation/path field
    into a SmartDeck projection.
    """
    if not isinstance(event, dict) or not isinstance(event.get("kind"), str):
        return None
    kind = event["kind"]
    if kind == "no_school":
        label = event.get("label")
        subtype = event.get("source_subtype")
        start = _normalized_date(event.get("start"))
        end = _normalized_date(event.get("end"))
        if not isinstance(label, str) or not isinstance(subtype, str) or not start or not end:
            return None
        if end < start:
            return None
        return {"kind": kind, "label": label, "start": start, "end": end,
                "source_subtype": subtype}
    if kind == "grading_period_end":
        label = event.get("label")
        code = event.get("code")
        end = _normalized_date(event.get("end"))
        if not isinstance(label, str) or not isinstance(code, str) or not end:
            return None
        return {"kind": kind, "label": label, "code": code, "end": end}
    if kind == "report_card":
        label = event.get("label")
        code = event.get("code")
        issue_date = _normalized_date(event.get("report_issue_date"))
        if not isinstance(label, str) or not isinstance(code, str) or not issue_date:
            return None
        return {"kind": kind, "label": label, "code": code,
                "report_issue_date": issue_date}
    return None


def _normalized_events(events) -> list[dict]:
    if not isinstance(events, (list, tuple)):
        return []
    return [normalized for event in events
            if (normalized := _normalize_event(event)) is not None]


def _event_sort_key(event: dict) -> tuple[str, str, str, str]:
    return (event.get("start") or event.get("end") or event.get("report_issue_date"),
            event["kind"], event.get("label", ""), event.get("code", ""))


def get_calendars() -> dict:
    calendars = _io_mod._synced_state().get("calendars", {})
    if not isinstance(calendars, dict):
        return {}
    result = {}
    for key, calendar in calendars.items():
        if not isinstance(calendar, dict):
            continue
        public = dict(calendar)
        public["events"] = _normalized_events(calendar.get("events", []))
        result[key] = public
    return result


def set_calendar(key: str, label: str, dates: list,
                 periods: list | None = None, events: list | None = None) -> None:
    def mutate(state):
        state.setdefault("calendars", {})[key] = {
            "label":          label,
            "no_count_dates": sorted(set(dates)),
            "grading_periods": periods or [],
            "events": _normalized_events(events),
        }

    _io_mod._modify_synced(mutate)


def remove_calendar(key: str) -> None:
    def mutate(state):
        state.setdefault("calendars", {}).pop(key, None)

    _io_mod._modify_synced(mutate)


def clear_all_calendars() -> None:
    _io_mod._modify_synced(
        lambda state: state.__setitem__("calendars", {}) or state
    )


def get_combined_calendar_for_range(
        date_from: str | None = None,
        date_to:   str | None = None) -> dict:
    no_count: set = set()
    periods:  list = []
    events: list = []
    calendars = _io_mod._synced_state().get("calendars", {})
    if not isinstance(calendars, dict):
        calendars = {}
    for cal in calendars.values():
        if not isinstance(cal, dict):
            continue
        for d in cal.get("no_count_dates", []):
            if date_from and d < date_from: continue
            if date_to   and d > date_to:   continue
            no_count.add(d)
        for gp in cal.get("grading_periods", []):
            if date_from and gp["end"]   < date_from: continue
            if date_to   and gp["start"] > date_to:   continue
            periods.append(gp)
        for event in _normalized_events(cal.get("events", [])):
            when = event.get("start") or event.get("end") or event.get("report_issue_date")
            until = event.get("end") or when
            if (date_from and until < date_from) or (date_to and when > date_to):
                continue
            events.append(event)
    unique_events = {tuple(sorted(event.items())): event for event in events}
    return {
        "no_count_dates": sorted(no_count),
        "grading_periods": sorted(periods, key=lambda p: p["start"]),
        "events": sorted(unique_events.values(), key=_event_sort_key),
    }
