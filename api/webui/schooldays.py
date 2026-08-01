"""School-day date math — calendar-aware lateness + date arithmetic.

Pure: callers pass a `no_count_dates` set (the canonical calendar's no_school
and no_regular_classes dates for the relevant range, from a checked seam such
as `api.webui.school_calendar.resolve_instructional_range()`) instead of a
weekend-skipping flag plus a parallel holiday list. One calendar decides what
a no-count day is; this module only does the arithmetic. Most callers that need
coverage/unknown-schedule failure handling should prefer
`school_calendar.add_school_days_checked()`/`count_school_days_checked()`
over calling these pure helpers directly with a hand-fetched set.
"""
from datetime import datetime, timedelta


def _parse_iso_local(s):
    """Canvas ISO timestamp → datetime in the machine's local timezone.
    Local matters: a 23:59 CST due date is 05:59Z the NEXT day — weekday and
    holiday checks must happen in school-local time."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


def _is_school_day(d, no_count_dates):
    return d.isoformat() not in no_count_dates


def _school_days_late(due_dt, submitted_dt, no_count_dates):
    """School days in (due_date, submitted_date] — next school day = 1 late."""
    if submitted_dt.date() <= due_dt.date():
        return 0
    n, d = 0, due_dt.date()
    while d < submitted_dt.date():
        d += timedelta(days=1)
        if _is_school_day(d, no_count_dates):
            n += 1
    return n


def _school_days_late_detail(due_dt, submitted_dt, no_count_dates):
    """Returns (school_days_late, excluded_list).
    excluded_list: ["YYYY-MM-DD (no-count)", ...]"""
    if submitted_dt.date() <= due_dt.date():
        return 0, []
    n, d, excluded = 0, due_dt.date(), []
    while d < submitted_dt.date():
        d += timedelta(days=1)
        if _is_school_day(d, no_count_dates):
            n += 1
        else:
            excluded.append(f"{d.isoformat()} (no-count)")
    return n, excluded


def _add_school_days(start_dt, days, no_count_dates):
    d, added = start_dt, 0
    while added < days:
        d += timedelta(days=1)
        if _is_school_day(d.date(), no_count_dates):
            added += 1
    return d
