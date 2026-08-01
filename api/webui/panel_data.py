"""Pure data projections for the public Calendar Panels.

The route module owns URLs and course/schedule resolution.  This module owns
the small, disk-read seams and the classroom-facing projections that turn the
canonical School Calendar into panel payloads.  Every public payload is calm:
it returns ``ok`` and a named state with empty collections when a local source
is unavailable or malformed.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from api import audience
from api.mirror import read_service
from api.course_catalog import read_catalog
from api.webui import deps, school_calendar


DEFAULT_DUE_DAYS = 7
MAX_DUE_DAYS = 31
DEFAULT_UPCOMING_DAYS = 14
MAX_UPCOMING_DAYS = 60
DEFAULT_SPORTS_DAYS = 14
MAX_SPORTS_DAYS = 90

_CALENDAR_STATES = {
    "unconfigured", "invalid_calendar", "outside_coverage", "unknown_schedule",
    "no_school", "no_regular_classes", "ready",
}


def clamp_days(value, default: int, maximum: int) -> int:
    """Return a safe positive integer for a hand-edited Panel URL."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(1, min(number, maximum))


def _local_date(now=None) -> date:
    if now is None:
        return datetime.now().astimezone().date()
    if isinstance(now, datetime) and now.tzinfo is not None:
        return now.astimezone().date()
    return now.date() if isinstance(now, datetime) else date.today()


def _local_time(now=None) -> str:
    if now is None:
        return datetime.now().astimezone().strftime("%H:%M")
    if isinstance(now, datetime) and now.tzinfo is not None:
        return now.astimezone().strftime("%H:%M")
    return now.strftime("%H:%M") if isinstance(now, datetime) else datetime.now().strftime("%H:%M")


def _iso(value) -> str:
    return value.isoformat() if isinstance(value, date) else str(value or "")


def _parse_iso(value) -> date | None:
    try:
        parsed = date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.isoformat() == str(value) else None


def _projection_result(result) -> tuple[dict | None, list]:
    if isinstance(result, tuple):
        projection = result[0] if result else None
        problems = result[1] if len(result) > 1 else []
        return projection if isinstance(projection, dict) else None, problems if isinstance(problems, list) else []
    return result if isinstance(result, dict) else None, []


def _projection(start: date, end: date, reader=None) -> tuple[dict | None, str | None]:
    source = reader or (lambda first, last: school_calendar.range_projection(
        first, last))
    try:
        projection, problems = _projection_result(source(start.isoformat(), end.isoformat()))
    except Exception:
        return None, "calendar_needs_attention"
    if projection is not None:
        return projection, None
    for problem in problems:
        if problem in _CALENDAR_STATES:
            return None, problem
    return None, "calendar_needs_attention"


def _read_calendar(reader=None) -> tuple[dict | None, str | None]:
    source = reader or school_calendar.read
    try:
        result = source()
        if isinstance(result, tuple):
            document = result[0] if result else None
            problems = result[1] if len(result) > 1 else []
        else:
            document, problems = result, []
    except Exception:
        return None, "calendar_needs_attention"
    if isinstance(document, dict):
        return document, None
    for problem in problems if isinstance(problems, list) else []:
        if problem in _CALENDAR_STATES:
            return None, problem
    return None, "calendar_needs_attention"


def _untagged(item: dict) -> dict:
    return {key: value for key, value in item.items() if key != "audience"}


def _event_date(event: dict) -> str:
    return str(event.get("date") or event.get("start") or event.get("end")
               or event.get("report_issue_date") or "")


def _sort_key(event: dict) -> tuple:
    return (_event_date(event), str(event.get("end") or ""),
            str(event.get("kind") or ""), str(event.get("label") or "").casefold(),
            str(event.get("detail") or "").casefold(), str(event.get("id") or ""))


def _academic_events(projection: dict) -> list[dict]:
    """Synthesize the structural facts for the public Panel union.

    This deliberately supersedes the older SmartDeck helper because
    ``no_regular_classes`` is a classroom ``day_type`` rather than a holiday.
    The source kind is stamped below, so stored audience claims are ignored.
    """
    events = []
    for day_key, entry in (projection.get("days") or {}).items():
        if not isinstance(entry, dict) or not entry.get("label"):
            continue
        if entry.get("kind") == "no_school":
            kind = "no_school"
        elif entry.get("kind") == "no_regular_classes":
            kind = "day_type"
        else:
            continue
        events.append({"kind": kind, "label": entry["label"],
                       "start": day_key, "end": day_key})
    for period in projection.get("grading_periods") or []:
        if not isinstance(period, dict):
            continue
        label = period.get("name") or period.get("code") or ""
        events.append({"kind": "grading_period_end", "label": label,
                       "code": period.get("code", ""), "end": period.get("end", "")})
        if period.get("report_issue_date"):
            events.append({"kind": "report_card", "label": label,
                           "code": period.get("code", ""),
                           "report_issue_date": period["report_issue_date"]})
    return events


def _fact_in_window(event: dict, start: date, end: date) -> bool:
    found = _parse_iso(_event_date(event))
    return bool(found and start <= found <= end)


def upcoming_events_payload(days=DEFAULT_UPCOMING_DAYS, *, now=None,
                            projection_reader=None) -> dict:
    """The classroom-safe Calendar/academic-date union for the forward window."""
    days = clamp_days(days, DEFAULT_UPCOMING_DAYS, MAX_UPCOMING_DAYS)
    start = _local_date(now)
    end = start + timedelta(days=days)
    projection, failure = _projection(start, end, projection_reader)
    if projection is None:
        return {"ok": True, "state": failure or "calendar_needs_attention",
                "days": days, "events": [],
                "message": "Calendar needs attention. Open Calendar in Canvas Expert."}

    raw = [event for event in (projection.get("events") or [])
           if isinstance(event, dict)]
    raw.extend(event for event in _academic_events(projection)
               if _fact_in_window(event, start, end))
    safe = audience.classroom_only([audience.tag(dict(event)) for event in raw])
    events = [_untagged(event) for event in sorted(safe, key=_sort_key)]
    return {"ok": True, "state": "ready" if events else "nothing_upcoming",
            "days": days, "events": events,
            "message": "" if events else f"Nothing scheduled in the next {days} days."}


def _weekday_occurrence(event: dict, start: date, end: date, *, newest=False) -> date | None:
    weekdays = event.get("weekdays")
    if not isinstance(weekdays, list):
        return None
    allowed = {value for value in weekdays if isinstance(value, int) and 0 <= value <= 6}
    effective_start = _parse_iso(event.get("effective_start"))
    effective_end = _parse_iso(event.get("effective_end"))
    days = []
    current = start
    while current <= end:
        if (current.weekday() in allowed
                and (effective_start is None or current >= effective_start)
                and (effective_end is None or current <= effective_end)):
            days.append(current)
        current += timedelta(days=1)
    return (days[-1] if newest else days[0]) if days else None


def _game_date(event: dict, start: date, end: date) -> date | None:
    shape = event.get("shape")
    if shape == "weekdays":
        return _weekday_occurrence(event, start, end, newest=True)
    value = event.get("date") or event.get("start")
    found = _parse_iso(value)
    return found if found and start <= found <= end else None


def sports_results_payload(days=DEFAULT_SPORTS_DAYS, *, now=None,
                           projection_reader=None) -> dict:
    """Recent canonical games with a non-empty result, newest first."""
    days = clamp_days(days, DEFAULT_SPORTS_DAYS, MAX_SPORTS_DAYS)
    end = _local_date(now)
    start = end - timedelta(days=days)
    projection, failure = _projection(start, end, projection_reader)
    if projection is None:
        return {"ok": True, "state": failure or "calendar_needs_attention",
                "days": days, "games": [],
                "message": "Calendar needs attention. Open Calendar in Canvas Expert."}

    games = []
    for source in projection.get("events") or []:
        if not isinstance(source, dict) or source.get("kind") != "game":
            continue
        result = source.get("result")
        if not isinstance(result, str) or not result.strip():
            continue
        occurred = _game_date(source, start, end)
        if occurred is None:
            continue
        item = _untagged(audience.tag(dict(source)))
        item["date"] = occurred.isoformat()
        games.append(item)
    games.sort(key=lambda item: (-(_parse_iso(item.get("date")) or date.min).toordinal(),
                                 str(item.get("label") or "").casefold(),
                                 str(item.get("detail") or "").casefold(),
                                 str(item.get("id") or "")))
    return {"ok": True, "state": "ready" if games else "no_results",
            "days": days, "games": games,
            "message": "" if games else f"No sports results in the last {days} days."}


def _reader_value(result, default):
    if isinstance(result, tuple):
        return result[0] if result else default
    return result if result is not None else default


def _empty_bobcat(state: str, *, day: date, message: str) -> dict:
    groups = {"A": {"tutorial": [], "club": []},
              "B": {"tutorial": [], "club": []}}
    return {"ok": True, "state": state, "date": day.isoformat(),
            "current_block": None, "groups": groups, "activities": [],
            "message": message}


def _event_occurs_on(event: dict, day: date) -> bool:
    shape = event.get("shape")
    if shape == "date":
        return event.get("date") == day.isoformat()
    if shape == "span":
        start = _parse_iso(event.get("start"))
        end = _parse_iso(event.get("end"))
        return bool(start and end and start <= day <= end)
    if shape == "weekdays":
        return bool(_weekday_occurrence(event, day, day))
    return False


def bobcat_hour_payload(*, now=None, calendar_reader=None,
                        bell_schedule_reader=None, projection_reader=None) -> dict:
    """Project today's canonical tutorial/club events into Bobcat A/B blocks."""
    day = _local_date(now)
    document, failure = _read_calendar(calendar_reader)
    if document is None:
        return _empty_bobcat(failure or "calendar_needs_attention", day=day,
                             message="Calendar needs attention. Open Calendar in Canvas Expert.")

    schedule_source = bell_schedule_reader or deps.load_bell_schedules
    try:
        schedules = _reader_value(schedule_source(), {})
    except Exception:
        schedules = {}
    schedules = schedules if isinstance(schedules, dict) else {}
    resolution = school_calendar.resolve_date(document, day.isoformat(), schedules.keys())
    state = resolution.get("state")
    if state != "ready":
        message = {
            "no_school": "No school today.",
            "no_regular_classes": "No regular classes today.",
        }.get(state, "Calendar needs attention. Open Calendar in Canvas Expert.")
        return _empty_bobcat(state or "calendar_needs_attention", day=day, message=message)
    if resolution.get("schedule_id") != "bell_schedule_bobcat_hour":
        return _empty_bobcat("not_bobcat_hour_day", day=day,
                             message="Today uses another Bell Schedule.")

    meetings = schedules.get("bell_schedule_bobcat_hour") or []
    slots = {}
    for meeting in meetings:
        if not isinstance(meeting, dict):
            continue
        period_id = str(meeting.get("period_id") or "")
        if period_id in ("bobcat_a", "bobcat_b"):
            slots[period_id[-1].upper()] = meeting
    if set(slots) != {"A", "B"}:
        return _empty_bobcat("calendar_needs_attention", day=day,
                             message="Bobcat Hour Bell Schedule needs attention.")

    projection, failure = _projection(day, day, projection_reader)
    if projection is None:
        return _empty_bobcat(failure or "calendar_needs_attention", day=day,
                             message="Calendar needs attention. Open Calendar in Canvas Expert.")

    groups = {"A": {"tutorial": [], "club": []},
              "B": {"tutorial": [], "club": []}}
    for source in projection.get("events") or []:
        if not isinstance(source, dict) or source.get("kind") not in ("tutorial", "club"):
            continue
        if not _event_occurs_on(source, day):
            continue
        start = str(source.get("from") or "")
        end = str(source.get("to") or "")
        if not start or not end or start >= end:
            continue
        slot = next((name for name, meeting in slots.items()
                     if start >= str(meeting.get("start") or "")
                     and end <= str(meeting.get("end") or "")), None)
        if slot is None:
            continue
        item = _untagged(audience.tag(dict(source)))
        item = {key: item[key] for key in
                ("id", "kind", "label", "detail", "from", "to") if key in item}
        groups[slot][source["kind"]].append(item)

    for slot in groups:
        for kind in groups[slot]:
            groups[slot][kind].sort(key=lambda item: (
                str(item.get("label") or "").casefold(),
                str(item.get("detail") or "").casefold(),
                str(item.get("id") or "")))
    activities = []
    for slot in ("A", "B"):
        for kind in ("tutorial", "club"):
            for item in groups[slot][kind]:
                activities.append({**item, "slot": slot})
    current = _local_time(now)
    current_block = next((slot for slot, meeting in slots.items()
                          if str(meeting.get("start") or "") <= current < str(meeting.get("end") or "")), None)
    state = "ready" if activities else "nothing_scheduled"
    return {"ok": True, "state": state, "date": day.isoformat(),
            "current_block": current_block, "groups": groups,
            "activities": activities,
            "message": "" if activities else "No tutorial or club blocks today."}


def _parse_due(value):
    """A Canvas ``due_at`` as an aware UTC datetime, or None."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    from datetime import timezone
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def whats_due_payload(course_id: str, days: int, *, now=None,
                      catalog_reader=None) -> dict:
    """Existing What's due projection, retained here with its shipped contract."""
    from datetime import timezone
    now = now or datetime.now(timezone.utc)
    local_now = now.astimezone()
    today = local_now.date()
    days = clamp_days(days, DEFAULT_DUE_DAYS, MAX_DUE_DAYS)
    horizon_date = today + timedelta(days=days)
    if not course_id:
        return {"ok": True, "state": "no_course", "days": days,
                "assignments": [], "message": "Choose a course for this panel."}
    reader = catalog_reader or (lambda cid: read_catalog(cid))
    read_result = reader(course_id)
    scope = read_service.catalog_assignments(course_id, catalog_reader=reader)
    if scope.get("source") == "none":
        return {"ok": True, "state": "no_catalog", "days": days,
                "assignments": [], "message": "No local course catalog yet. Refresh it in "
                "CanvasExpert, then this panel fills in."}
    catalog = (read_result or {}).get("catalog") or {}
    items = []
    for record in scope.get("records") or []:
        if not isinstance(record, dict) or not record.get("published", True):
            continue
        due = _parse_due(record.get("due_at"))
        if due is None:
            continue
        due_date = due.astimezone().date()
        if due_date < today or due_date > horizon_date:
            continue
        items.append({"title": str(record.get("name") or "Untitled assignment"),
                      "due_at": due.isoformat(), "points": record.get("points_possible"),
                      "_earlier_today": due_date == today and due < now})
    items.sort(key=lambda item: (item["_earlier_today"], item["due_at"]))
    for item in items:
        del item["_earlier_today"]
    return {"ok": True, "state": "ready" if items else "nothing_due",
            "days": days, "course_name": str(catalog.get("course_name") or ""),
            "synced_at": scope.get("last_success_at", ""),
            "stale": scope.get("state") != "current", "assignments": items,
            "message": "" if items else f"Nothing due in the next {days} days."}
