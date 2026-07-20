"""School-day date math — weekend/holiday-aware lateness + date arithmetic.

Extracted verbatim from server.py's Gradebook section so the logic is
importable and unit-testable on its own. No behavior change. Names keep their
leading underscore so existing call sites stay untouched.
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


def _is_school_day(d, skip_weekends, holidays):
    if skip_weekends and d.weekday() >= 5:
        return False
    return d.isoformat() not in holidays


def _school_days_late(due_dt, submitted_dt, skip_weekends, holidays):
    """School days in (due_date, submitted_date] — next school day = 1 late."""
    if submitted_dt.date() <= due_dt.date():
        return 0
    n, d = 0, due_dt.date()
    while d < submitted_dt.date():
        d += timedelta(days=1)
        if _is_school_day(d, skip_weekends, holidays):
            n += 1
    return n


def _school_days_late_detail(due_dt, submitted_dt, skip_weekends, holidays):
    """Returns (school_days_late, excluded_list).
    excluded_list: ["YYYY-MM-DD (weekend)", "YYYY-MM-DD (holiday)", ...]"""
    if submitted_dt.date() <= due_dt.date():
        return 0, []
    n, d, excluded = 0, due_dt.date(), []
    while d < submitted_dt.date():
        d += timedelta(days=1)
        if _is_school_day(d, skip_weekends, holidays):
            n += 1
        else:
            reason = "weekend" if d.weekday() >= 5 else "holiday"
            excluded.append(f"{d.isoformat()} ({reason})")
    return n, excluded


def _add_school_days(start_dt, days, skip_weekends, holidays):
    d, added = start_dt, 0
    while added < days:
        d += timedelta(days=1)
        if _is_school_day(d.date(), skip_weekends, holidays):
            added += 1
    return d