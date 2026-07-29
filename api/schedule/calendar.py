"""No-school dates, borrowed from the academic calendar already in the app.

This is the only file in `api/schedule/` that reaches outside itself. The
academic calendar in `api/webui/config/calendars.py` already holds the district
no-count dates that the sweep and extension features use, so duplicating that
list here would guarantee the two drift apart.

Two deliberate choices:

* `api.webui.config` is imported inside the function rather than at module top
  level. That package reaches `keyring` through `config/_io.py`, and the rest of
  `api/schedule/` has to stay importable in a bare context with no credential
  store present.
* Nothing here raises. A missing or unconfigured calendar means "no known
  no-school dates", not an error. A teacher who never imported a calendar
  should still get a working screen, and a blank projector is a worse failure
  than a Saturday that thinks it is a school day.
"""
from __future__ import annotations

from datetime import date, datetime


def no_school_dates(date_from: date, date_to: date) -> frozenset[date]:
    """Non-instructional dates in the inclusive range, empty when unknown.

    The underlying call takes and returns "YYYY-MM-DD" strings, so this
    converts in both directions and drops anything unparseable rather than
    letting one bad row take the range with it.
    """
    payload = _combined_calendar(date_from, date_to)
    raw = payload.get("no_count_dates") if isinstance(payload, dict) else None
    if not isinstance(raw, (list, tuple, set, frozenset)):
        return frozenset()

    found: set[date] = set()
    for value in raw:
        parsed = _parse(value)
        if parsed is not None and date_from <= parsed <= date_to:
            found.add(parsed)
    return frozenset(found)


def _combined_calendar(date_from: date, date_to: date) -> dict:
    try:
        from api.webui import config
    except Exception:
        return {}
    try:
        payload = config.get_combined_calendar_for_range(
            date_from=date_from.isoformat(),
            date_to=date_to.isoformat(),
        )
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None
