"""Calendar-only board projection for the Glass display."""

from __future__ import annotations

from datetime import date, timedelta

from . import clock_time, deps, glass, school_calendar


DEFAULT_FORWARD_DAYS = 14
DEFAULT_SPORTS_DAYS = 14
_UNSET = object()


def get_board_context(
    at=None,
    *,
    calendar_document=_UNSET,
    bell_schedules=_UNSET,
    teacher_schedule=_UNSET,
) -> dict:
    """Return the Glass context plus its school-facing calendar regions."""
    local_at, _simulated = glass.normalize_at(at)
    if calendar_document is _UNSET:
        calendar_document, _calendar_problems = school_calendar.read()
    if bell_schedules is _UNSET:
        bell_schedules, _bell_problems = deps.load_bell_schedules()
    if teacher_schedule is _UNSET:
        teacher_schedule, _teacher_problems = deps.load_teacher_schedule()

    bell_schedules = bell_schedules if isinstance(bell_schedules, dict) else {}
    teacher_schedule = teacher_schedule if isinstance(teacher_schedule, dict) else {}
    context = glass.get_current_context(
        at,
        calendar_document=calendar_document,
        bell_schedules=bell_schedules,
        teacher_schedule=teacher_schedule,
    )
    board = _empty_board(context["state"])
    board["schedule_label"] = _schedule_label(context.get("schedule_id"))

    if not isinstance(calendar_document, dict):
        board["message"] = _state_message(context["state"])
        return {"context": context, "board": board}

    today = local_at.date()
    forward_end = today + timedelta(days=DEFAULT_FORWARD_DAYS)
    past_start = today - timedelta(days=DEFAULT_SPORTS_DAYS)
    events = [event for event in calendar_document.get("events", [])
              if isinstance(event, dict)]

    board.update({
        "state": context["state"],
        "message": _state_message(context["state"]),
        "today_events": _event_items_on(events, today),
        "forward_events": _event_items_between(events, today + timedelta(days=1), forward_end),
        "academic_dates": _academic_dates(calendar_document, today, forward_end),
        "sports_results": _sports_results(events, past_start, today),
        "bobcat": _bobcat_activities(
            events,
            today,
            local_at,
            context,
            bell_schedules,
        ),
        "grading_period": _grading_period(calendar_document, today),
    })
    return {"context": context, "board": board}


def get_display_context(
    at=None,
    *,
    calendar_document=_UNSET,
    bell_schedules=_UNSET,
    teacher_schedule=_UNSET,
    scope_reader=None,
    catalog_reader=None,
    objective_reader=None,
    profile_reader=None,
) -> dict:
    """Return board mode, or add the private class projection when in class mode."""
    board_kwargs = {}
    if calendar_document is not _UNSET:
        board_kwargs["calendar_document"] = calendar_document
    if bell_schedules is not _UNSET:
        board_kwargs["bell_schedules"] = bell_schedules
    if teacher_schedule is not _UNSET:
        board_kwargs["teacher_schedule"] = teacher_schedule
    payload = get_board_context(at, **board_kwargs)
    if payload.get("context", {}).get("mode") != "class":
        return payload
    from . import glass_class

    payload["classroom"] = glass_class.get_class_context(
        payload["context"],
        at=at,
        scope_reader=scope_reader,
        catalog_reader=catalog_reader,
        objective_reader=objective_reader,
        profile_reader=profile_reader,
    )
    return payload


def _empty_board(state):
    return {
        "state": state,
        "message": "",
        "schedule_label": "",
        "today_events": [],
        "forward_events": [],
        "academic_dates": [],
        "sports_results": [],
        "bobcat": {"state": "not_available", "current_block": None, "activities": []},
        "grading_period": {"state": "none"},
    }


def _event_items_on(events, day):
    return [_event_item(event, day) for event in events if _event_occurs_on(event, day)]


def _event_items_between(events, start, end):
    items = []
    for event in events:
        occurrences = _event_occurrences(event, start, end)
        if occurrences:
            items.append(_event_item(event, occurrences[0]))
    return sorted(items, key=_item_sort_key)


def _event_item(event, occurrence):
    item = {"date": occurrence.isoformat()}
    for key in ("id", "kind", "label", "detail", "from", "to"):
        if key in event:
            item[key] = event[key]
    if event.get("shape") == "span":
        item["start"] = event.get("start")
        item["end"] = event.get("end")
    return item


def _event_occurs_on(event, day):
    return day in _event_occurrences(event, day, day)


def _event_occurrences(event, start, end):
    shape = event.get("shape")
    if shape == "date":
        found = _parse_date(event.get("date"))
        return [found] if found and start <= found <= end else []
    if shape == "span":
        span_start = _parse_date(event.get("start"))
        span_end = _parse_date(event.get("end"))
        if not span_start or not span_end or span_end < start or span_start > end:
            return []
        return [max(start, span_start)]
    if shape == "weekdays":
        weekdays = {value for value in event.get("weekdays", [])
                    if isinstance(value, int) and 0 <= value <= 6}
        effective_start = _parse_date(event.get("effective_start"))
        effective_end = _parse_date(event.get("effective_end"))
        occurrences = []
        cursor = start
        while cursor <= end:
            if (cursor.weekday() in weekdays
                    and (effective_start is None or cursor >= effective_start)
                    and (effective_end is None or cursor <= effective_end)):
                occurrences.append(cursor)
            cursor += timedelta(days=1)
        return occurrences
    return []


def _academic_dates(document, today, end):
    items = []
    for period in document.get("grading_periods", []):
        if not isinstance(period, dict):
            continue
        for field, label in (
            ("start", "starts"),
            ("end", "ends"),
            ("report_issue_date", "report cards"),
        ):
            found = _parse_date(period.get(field))
            if found and today <= found <= end:
                items.append({
                    "date": found.isoformat(),
                    "label": f"{period.get('name') or period.get('code') or 'Grading period'} {label}",
                    "kind": "academic_date",
                })
    return sorted(items, key=lambda item: (item["date"], item["label"].casefold()))


def _sports_results(events, start, end):
    items = []
    for event in events:
        if event.get("kind") != "game" or not str(event.get("result") or "").strip():
            continue
        occurrences = _event_occurrences(event, start, end)
        if not occurrences:
            continue
        item = _event_item(event, occurrences[-1])
        item["result"] = event.get("result") or ""
        items.append(item)
    return sorted(items, key=lambda item: (
        item["date"], str(item.get("label") or "").casefold()
    ), reverse=True)


def _bobcat_activities(events, day, local_at, context, schedules):
    if not context.get("schedule_id"):
        return {"state": context.get("state") or "not_available", "current_block": None, "activities": []}
    meetings = schedules.get(context.get("schedule_id"), [])
    bobcat = [meeting for meeting in meetings if str(meeting.get("period_id") or "").casefold().startswith("bobcat")]
    if not bobcat:
        return {"state": "not_bobcat_hour", "current_block": None, "activities": []}

    current_minute = local_at.hour * 60 + local_at.minute
    current_block = None
    slot_meetings = []
    for meeting in bobcat:
        start = clock_time.parse_time(meeting.get("start"))
        end = clock_time.parse_time(meeting.get("end"))
        if start is None or end is None or end <= start:
            continue
        period_id = str(meeting.get("period_id") or "")
        slot = period_id.rsplit("_", 1)[-1].upper() if "_" in period_id else (meeting.get("segment") or "Bobcat Hour")
        slot_meetings.append((slot, start, end))
        if start <= current_minute < end:
            current_block = slot

    activities = []
    for event in events:
        if event.get("kind") not in ("tutorial", "club") or not _event_occurs_on(event, day):
            continue
        start = clock_time.parse_time(event.get("from"))
        end = clock_time.parse_time(event.get("to"))
        slot = next((slot for slot, meeting_start, meeting_end in slot_meetings
                     if start is not None and end is not None
                     and meeting_start <= start and end <= meeting_end), None)
        if slot is None and start is None and end is None and len(slot_meetings) == 1:
            slot = slot_meetings[0][0]
        if slot is None:
            continue
        item = _event_item(event, day)
        item["slot"] = slot
        activities.append(item)
    activities.sort(key=lambda item: (
        str(item.get("from") or ""),
        str(item.get("slot") or ""),
        str(item.get("label") or "").casefold(),
    ))
    return {"state": "ready" if activities else "nothing_scheduled",
            "current_block": current_block, "activities": activities}


def _grading_period(document, day):
    periods = [period for period in document.get("grading_periods", [])
               if isinstance(period, dict)
               and _parse_date(period.get("start")) <= day <= _parse_date(period.get("end"))]
    if not periods:
        return {"state": "none"}
    period = periods[0]
    end = _parse_date(period.get("end"))
    return {
        "state": "ready",
        "code": period.get("code") or "",
        "name": period.get("name") or period.get("code") or "Grading period",
        "start": period.get("start") or "",
        "end": period.get("end") or "",
        "days_remaining": (end - day).days if end else None,
    }


def _schedule_label(schedule_id):
    value = str(schedule_id or "").strip().replace("_", " ")
    if value.casefold().startswith("bell schedule "):
        value = value[14:].strip()
    return value.title() or ""


def _parse_date(value):
    try:
        parsed = date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.isoformat() == str(value) else None


def _item_sort_key(item):
    return (str(item.get("date") or ""), str(item.get("label") or "").casefold())


def _state_message(state):
    return {
        "no_school": "No school today.",
        "no_regular_classes": "No regular classes today.",
        "unconfigured": "Calendar needs attention.",
        "invalid_calendar": "Calendar needs attention.",
        "outside_coverage": "Calendar needs attention.",
        "unknown_schedule": "Calendar needs attention.",
    }.get(state, "")
