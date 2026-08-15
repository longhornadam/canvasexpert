"""Resolve the current Glass classroom context from local schedule data.

This module is deliberately offline.  It reads the canonical school calendar,
the local Bell Schedules, and the local Teacher Schedule; it never reaches a
remote service.  The public entry point accepts an optional effective clock so
the same result can drive the classroom page and its simulator.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from . import clock_time, day_schedule, deps, school_calendar


LOCAL_TIMEZONE = "America/Chicago"
_UNSET = object()


def get_current_context(
    at=None,
    *,
    calendar_document=_UNSET,
    bell_schedules=_UNSET,
    teacher_schedule=_UNSET,
    resolved_at=None,
) -> dict:
    """Return the current Glass context.

    ``at`` is the effective local clock.  It may be an aware or naive
    ``datetime`` or an ISO timestamp string; naive values are interpreted in
    the school's local timezone.  Supplying it marks the response as
    simulated.  The keyword inputs are small test seams and are not another
    persisted source of truth.
    """
    local_at, simulated = normalize_at(at)

    if calendar_document is _UNSET:
        calendar_document, calendar_problems = school_calendar.read()
    else:
        calendar_problems = []
    if bell_schedules is _UNSET:
        bell_schedules, _bell_problems = deps.load_bell_schedules()
    if teacher_schedule is _UNSET:
        teacher_schedule, _teacher_problems = deps.load_teacher_schedule()

    bell_schedules = bell_schedules if isinstance(bell_schedules, dict) else {}
    teacher_schedule = teacher_schedule if isinstance(teacher_schedule, dict) else {}

    date_key = local_at.date().isoformat()
    if calendar_document is None:
        state = _calendar_failure_state(calendar_problems)
        return _empty_context(
            local_at,
            simulated,
            resolved_at=resolved_at,
            date_key=date_key,
            state=state,
            valid_until=_next_midnight(local_at),
        )

    resolution = school_calendar.resolve_date(
        calendar_document,
        date_key,
        bell_schedules.keys(),
    )
    day_entry = (
        calendar_document.get("days", {}).get(date_key)
        if isinstance(calendar_document.get("days"), dict)
        else None
    )
    common = {
        "date": date_key,
        "day_kind": day_entry.get("kind") if isinstance(day_entry, dict) else None,
        "schedule_id": resolution.get("schedule_id"),
        "day_label": resolution.get("label"),
    }

    if resolution.get("state") != "ready":
        return _empty_context(
            local_at,
            simulated,
            resolved_at=resolved_at,
            valid_until=_next_midnight(local_at),
            **common,
            state=resolution.get("state") or "invalid_calendar",
        )

    schedule_id = resolution["schedule_id"]
    meetings = bell_schedules.get(schedule_id) or []
    resolved_blocks, _resolve_problems = day_schedule.resolve_day(
        schedule_id,
        bell_schedules,
        teacher_schedule,
    )
    runs, lunch_intervals, unclaimed = _build_runs(
        meetings,
        resolved_blocks,
        teacher_schedule,
    )
    return _resolve_ready(
        local_at,
        simulated,
        resolved_at=resolved_at,
        common=common,
        meetings=meetings,
        runs=runs,
        lunch_intervals=lunch_intervals,
        unclaimed=unclaimed,
    )


def normalize_at(value=None):
    """Return the effective local clock and whether it was simulated."""
    return _effective_at(value)


def _resolve_ready(
    local_at,
    simulated,
    *,
    resolved_at,
    common,
    meetings,
    runs,
    lunch_intervals,
    unclaimed,
) -> dict:
    minute = local_at.hour * 60 + local_at.minute
    course_runs = [run for run in runs if run["course_id"]]
    current_course = _containing_run(course_runs, minute)
    current_run = current_course or _containing_run(runs, minute)

    if current_course is not None:
        state = "in_class"
        block = _public_block(current_course)
        valid_until = _at_clock_boundary(local_at, current_course["end"])
        next_run = _next_course_run(course_runs, current_course)
        next_block = _public_next(next_run)
    else:
        current_lunch = _containing_intervals(lunch_intervals, minute)
        if current_lunch:
            state = "lunch"
            block = None
            valid_until = _at_clock_boundary(local_at, min(end for _start, end in current_lunch))
            next_block = None
        else:
            current_unclaimed = _containing_intervals(unclaimed, minute)
            if current_run is not None:
                state = "free"
                block = None
                valid_until = _at_clock_boundary(local_at, current_run["end"])
                next_block = None
            elif current_unclaimed:
                state = "free"
                block = None
                valid_until = _at_clock_boundary(local_at, min(end for _start, end in current_unclaimed))
                next_block = None
            else:
                first_minute = _first_valid_minute(meetings)
                last_minute = _last_valid_end(meetings)
                if first_minute is not None and minute < first_minute:
                    state = "before_school"
                    valid_until = _at_clock_boundary(local_at, first_minute)
                    block = None
                    next_block = None
                elif last_minute is not None and minute >= last_minute:
                    state = "after_school"
                    valid_until = _next_midnight(local_at)
                    block = None
                    next_block = None
                else:
                    next_run = _next_course_run(course_runs, minute)
                    next_meeting = _next_meeting_start(meetings, minute)
                    if next_run is not None and next_meeting == next_run["start"]:
                        state = "up_next"
                        block = _public_block(next_run)
                        valid_until = _at_clock_boundary(local_at, next_run["start"])
                        next_block = _public_next(_next_course_run(course_runs, next_run))
                    else:
                        state = "free"
                        block = None
                        next_minute = next_meeting
                        valid_until = (
                            _at_clock_boundary(local_at, next_minute)
                            if next_minute is not None
                            else _next_midnight(local_at)
                        )
                        next_block = None

    return {
        "resolved_at": _resolved_timestamp(resolved_at),
        "at": _iso(local_at),
        "simulated": simulated,
        **common,
        "mode": "class" if state in {"in_class", "up_next"} else "board",
        "state": state,
        "block": block,
        "next": next_block if state in {"in_class", "up_next"} else None,
        "valid_until": _iso(valid_until),
    }


def _build_runs(meetings, resolved_blocks, teacher_schedule):
    """Build display runs and separate the raw unclaimed meetings.

    Lunch is an interval, not a replacement for the bell period around it.
    Subtracting it here keeps the teacher's class run honest even when a
    schedule represents lunch as an overlapping row inside 4th/5th.
    """
    valid_meetings = []
    for meeting in meetings:
        start = clock_time.parse_time(meeting.get("start"))
        end = clock_time.parse_time(meeting.get("end"))
        if start is None or end is None or end <= start:
            continue
        valid_meetings.append((meeting, start, end))

    teacher_blocks = teacher_schedule.get("blocks") or []
    claimed_periods = {
        str(period)
        for block in teacher_blocks
        if isinstance(block, dict)
        for period in (block.get("raw_periods") or [])
    }
    by_name = {
        block.get("name"): block
        for block in teacher_blocks
        if isinstance(block, dict) and block.get("name")
    }
    lunch_intervals = [
        (start, end)
        for meeting, start, end in valid_meetings
        if str(meeting.get("period_id", "")).strip().casefold() == "lunch"
    ]
    unclaimed = [
        (start, end)
        for meeting, start, end in valid_meetings
        if str(meeting.get("period_id")) not in claimed_periods
        and str(meeting.get("period_id", "")).strip().casefold() != "lunch"
    ]

    runs = []
    for resolved in resolved_blocks:
        start = clock_time.parse_time(resolved.get("start"))
        end = clock_time.parse_time(resolved.get("end"))
        if start is None or end is None or end <= start:
            continue
        owner = by_name.get(resolved.get("name"), {})
        course_id = owner.get("course_id") or None
        segments = _subtract_intervals(start, end, lunch_intervals)
        matching = [
            (meeting, meeting_start, meeting_end)
            for meeting, meeting_start, meeting_end in valid_meetings
            if meeting_start < end
            and meeting_end > start
            and str(meeting.get("period_id")) in {
                str(period_id) for period_id in (resolved.get("period_ids") or [])
            }
        ]
        for segment_start, segment_end in segments:
            period_ids = [
                str(meeting.get("period_id"))
                for meeting, meeting_start, meeting_end in matching
                if meeting_start < segment_end and meeting_end > segment_start
            ] or [str(period_id) for period_id in (resolved.get("period_ids") or [])]
            runs.append({
                "name": resolved.get("name") or "",
                "label": resolved.get("label") or "",
                "course_id": course_id,
                "period_ids": period_ids,
                "start": segment_start,
                "end": segment_end,
            })

    runs.sort(key=lambda run: (run["start"], run["end"], run["name"]))
    return runs, lunch_intervals, unclaimed


def _subtract_intervals(start, end, excluded):
    pieces = [(start, end)]
    for excluded_start, excluded_end in sorted(excluded):
        next_pieces = []
        for piece_start, piece_end in pieces:
            if excluded_end <= piece_start or excluded_start >= piece_end:
                next_pieces.append((piece_start, piece_end))
                continue
            if piece_start < excluded_start:
                next_pieces.append((piece_start, excluded_start))
            if excluded_end < piece_end:
                next_pieces.append((excluded_end, piece_end))
        pieces = next_pieces
    return [(piece_start, piece_end) for piece_start, piece_end in pieces if piece_start < piece_end]


def _containing_run(runs, minute):
    for run in runs:
        if run["start"] <= minute < run["end"]:
            return run
    return None


def _containing_intervals(intervals, minute):
    return [(start, end) for start, end in intervals if start <= minute < end]


def _next_course_run(runs, current_or_minute):
    threshold = (
        current_or_minute["end"]
        if isinstance(current_or_minute, dict)
        else current_or_minute
    )
    for run in runs:
        if run["start"] >= threshold:
            return run
    return None


def _public_block(run):
    return {
        "name": run["name"],
        "label": run["label"],
        "course_id": run["course_id"],
        "period_ids": list(run["period_ids"]),
        "starts_at": clock_time.format_time(run["start"]),
        "ends_at": clock_time.format_time(run["end"]),
    }


def _public_next(run):
    if run is None:
        return None
    return {
        "name": run["name"],
        "label": run["label"],
        "course_id": run["course_id"],
        "starts_at": clock_time.format_time(run["start"]),
    }


def _effective_at(value):
    simulated = value is not None
    zone = _local_zone()
    if value is None:
        current = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        current = value
    elif isinstance(value, str):
        text = value.strip()
        try:
            current = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("at must be an ISO timestamp") from exc
    else:
        raise ValueError("at must be an ISO timestamp or datetime")
    if current.tzinfo is None:
        current = current.replace(tzinfo=zone)
    return current.astimezone(zone).replace(microsecond=0), simulated


def _local_zone():
    try:
        return ZoneInfo(LOCAL_TIMEZONE)
    except Exception:
        return datetime.now().astimezone().tzinfo or timezone.utc


def _at_clock_boundary(local_at, minute):
    return datetime.combine(
        local_at.date(),
        time(hour=minute // 60, minute=minute % 60),
        tzinfo=local_at.tzinfo,
    )


def _next_midnight(local_at):
    return datetime.combine(
        local_at.date() + timedelta(days=1),
        time.min,
        tzinfo=local_at.tzinfo,
    )


def _first_valid_minute(meetings):
    starts = [clock_time.parse_time(meeting.get("start")) for meeting in meetings]
    starts = [minute for minute in starts if minute is not None]
    return min(starts) if starts else None


def _last_valid_end(meetings):
    ends = [clock_time.parse_time(meeting.get("end")) for meeting in meetings]
    ends = [minute for minute in ends if minute is not None]
    return max(ends) if ends else None


def _next_meeting_start(meetings, minute):
    starts = [clock_time.parse_time(meeting.get("start")) for meeting in meetings]
    starts = [start for start in starts if start is not None and start > minute]
    return min(starts) if starts else None


def _empty_context(
    local_at,
    simulated,
    *,
    resolved_at,
    valid_until,
    state,
    date=None,
    day_kind=None,
    schedule_id=None,
    day_label=None,
    date_key=None,
):
    return {
        "resolved_at": _resolved_timestamp(resolved_at),
        "at": _iso(local_at),
        "simulated": simulated,
        "date": date or date_key,
        "day_kind": day_kind,
        "schedule_id": schedule_id,
        "day_label": day_label,
        "mode": "board",
        "state": state,
        "block": None,
        "next": None,
        "valid_until": _iso(valid_until),
    }


def _calendar_failure_state(problems):
    if problems and problems[0] in {"unconfigured", "invalid_calendar"}:
        return problems[0]
    return "unconfigured"


def _resolved_timestamp(value):
    if value is None:
        current = datetime.now(timezone.utc).astimezone(_local_zone())
        return _iso(current.replace(microsecond=0))
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=_local_zone())
        return _iso(value.astimezone(_local_zone()).replace(microsecond=0))
    return str(value)


def _iso(value):
    return value.isoformat(timespec="seconds")
