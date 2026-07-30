"""Read the school events a teacher records: games, dances, tutorials, clubs.

The district calendar CSV knows that a date is a no-school day and when report
cards go home. It does not know about picture day, a volleyball game, or when
the library opens early. Those facts have had nowhere to live, so the only way
to get one onto a projector was to author a whole dated scene with the words
typed into a pane. This file is where they live instead.

Deliberately a sibling of `calendar_csv.py` rather than an addition to it. That
parser feeds `no_count_dates`, which nine late-work call sites depend on, so it
stays boring. Nothing here touches it, and a dance never cancels class.

Pure stdlib, no app imports at module level, same posture as its neighbour. One
fixed filename, read fresh on every query -- unlike the CSV, which is parsed
once at import and persisted, so adding a game would otherwise mean re-importing
a calendar.

Nothing here raises. A malformed file means "no school events", not an error: a
teacher who fat-fingers a date should get a screen missing one line, not a blank
wall.
"""
from __future__ import annotations

import json
import os
from datetime import date, time

SCHOOL_EVENTS_FORMAT = "canvasexpert.school_events/1"
SCHOOL_EVENTS_FILENAME = "school-events.json"

# How far ahead a screen looks by default. Matches the MCP Glass context tool's
# own default so the two surfaces agree about what "upcoming" means; a
# term-length view is a different product.
DEFAULT_LOOKAHEAD_DAYS = 14

# The closed set of things a teacher can record. Closed on purpose: an open
# vocabulary would drift into a taxonomy nobody maintains, and `api/audience.py`
# has to be able to say whether each one may reach a wall.
#
# These are events on a date. They are not bell-schedule blocks -- `BlockKind`
# in `api/schedule/models.py` names stretches of a school day, and conflating
# the two is how "assembly" starts meaning two different things.
EVENT_KINDS = frozenset({
    "game", "dance", "assembly", "performance", "spirit",
    "tutorial", "club", "library", "other",
})


def _is_comment_key(key: object) -> bool:
    """True for the `_comment` and `_example_events` keys the template carries.

    The shipped file explains itself inline, which is worth more to a teacher
    than a tidy parser. The same underscore convention as the bell schedule
    template, and the reason the populated example in the shipped file is
    structurally unreadable rather than merely fictional.
    """
    return isinstance(key, str) and key.startswith("_")


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _parse_date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(_text(value))
    except ValueError:
        return None


def _parse_time(value: object) -> str:
    """An HH:MM string, or empty when absent or unparseable.

    Kept as text rather than a `time` because the only consumer prints it, and
    a string survives JSON round-tripping into a pane without a codec.
    """
    text = _text(value)
    if not text:
        return ""
    try:
        return time.fromisoformat(text).isoformat(timespec="minutes")
    except ValueError:
        return ""


def _parse_weekdays(value: object) -> tuple[int, ...]:
    """Sorted, de-duplicated weekday numbers; empty when unusable.

    0 is Monday through 6 Sunday, matching `datetime.date.weekday()` and the
    bell schedule's `weekday_default`, so a teacher who has seen one file's
    numbering has seen both.
    """
    if not isinstance(value, (list, tuple)):
        return ()
    found = set()
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int):
            continue
        if 0 <= item <= 6:
            found.add(item)
    return tuple(sorted(found))


def _parse_effective(value: object) -> tuple[date | None, date | None]:
    """The optional window a recurring event is active in."""
    if not isinstance(value, dict):
        return (None, None)
    return (_parse_date(value.get("start")), _parse_date(value.get("end")))


def parse_event(raw: object) -> dict | None:
    """One validated event, or None when the entry is unusable.

    Exactly one of three shapes, and never two at once: a single `date`, an
    inclusive `start`/`end` span, or a recurring `weekdays` list. An entry
    carrying more than one shape is ambiguous rather than generous, so it is
    dropped -- a teacher who wrote both meant something specific and should see
    the line missing and fix it.
    """
    if not isinstance(raw, dict):
        return None
    if all(map(_is_comment_key, raw)):
        return None

    kind = _text(raw.get("kind"))
    label = _text(raw.get("label"))
    if kind not in EVENT_KINDS or not label:
        return None

    single = _parse_date(raw.get("date")) if raw.get("date") is not None else None
    span_start = _parse_date(raw.get("start")) if raw.get("start") is not None else None
    span_end = _parse_date(raw.get("end")) if raw.get("end") is not None else None
    weekdays = _parse_weekdays(raw.get("weekdays"))

    shapes = sum((single is not None, span_start is not None or span_end is not None,
                  bool(weekdays)))
    if shapes != 1:
        return None

    event = {"kind": kind, "label": label, "detail": _text(raw.get("detail")),
             "from": _parse_time(raw.get("from")), "to": _parse_time(raw.get("to"))}

    if single is not None:
        event.update(shape="date", start=single.isoformat(), end=single.isoformat())
        return event

    if weekdays:
        window_start, window_end = _parse_effective(raw.get("effective"))
        if window_start and window_end and window_end < window_start:
            return None
        event.update(shape="weekly", weekdays=list(weekdays),
                     effective_start=window_start.isoformat() if window_start else "",
                     effective_end=window_end.isoformat() if window_end else "")
        return event

    if span_start is None or span_end is None or span_end < span_start:
        return None
    event.update(shape="span", start=span_start.isoformat(), end=span_end.isoformat())
    return event


def parse_school_events(payload: object) -> list[dict]:
    """Every usable event in a parsed file, dropping the rest."""
    if not isinstance(payload, dict):
        return []
    if payload.get("format") != SCHOOL_EVENTS_FORMAT:
        return []
    raw_events = payload.get("events")
    if not isinstance(raw_events, (list, tuple)):
        return []
    return [event for item in raw_events if (event := parse_event(item)) is not None]


def events_file_path(root=None) -> str | None:
    """Where the events file lives, or None when there is no workspace.

    Imported inside the function for the same reason `api/schedule/calendar.py`
    does it: the workspace module reaches configuration that reaches the
    credential store, and this file has to stay importable without one.
    """
    try:
        from api.webui import workspace
    except Exception:
        return None
    try:
        folder = workspace.library_folder("Calendars", root) if root else workspace.library_folder("Calendars")
    except Exception:
        return None
    if not folder:
        return None
    return os.path.join(folder, SCHOOL_EVENTS_FILENAME)


def read_school_events(path: str | None = None, root=None) -> list[dict]:
    """The events on disk, or an empty list when there are none to be had."""
    target = path or events_file_path(root)
    if not target or not os.path.isfile(target):
        return []
    try:
        with open(target, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return []
    return parse_school_events(payload)


def occurs_on(event: dict, day: date) -> bool:
    """True when this event is showing on `day`."""
    shape = event.get("shape")
    if shape in ("date", "span"):
        start = _parse_date(event.get("start"))
        end = _parse_date(event.get("end"))
        return bool(start and end and start <= day <= end)
    if shape == "weekly":
        if day.weekday() not in (event.get("weekdays") or []):
            return False
        window_start = _parse_date(event.get("effective_start"))
        window_end = _parse_date(event.get("effective_end"))
        if window_start and day < window_start:
            return False
        if window_end and day > window_end:
            return False
        return True
    return False


def events_for_range(date_from: date, date_to: date, *, path: str | None = None,
                     root=None) -> list[dict]:
    """Events showing at any point in the inclusive range.

    A span is one event, not one per day -- a wall wants "Spring Break, March 9
    to 13" as a single line. A recurring event is likewise one entry, carrying
    the weekdays it runs on; whoever renders it decides whether to say "Tuesdays
    and Thursdays" or to resolve the next occurrence.
    """
    if date_to < date_from:
        return []
    found = []
    for event in read_school_events(path, root):
        if _shows_in_range(event, date_from, date_to):
            found.append(event)
    return sorted(found, key=_sort_key)


def _shows_in_range(event: dict, date_from: date, date_to: date) -> bool:
    if event.get("shape") == "weekly":
        day = date_from
        while day <= date_to:
            if occurs_on(event, day):
                return True
            day = date.fromordinal(day.toordinal() + 1)
        return False
    start = _parse_date(event.get("start"))
    end = _parse_date(event.get("end"))
    if not start or not end:
        return False
    return not (end < date_from or start > date_to)


def _sort_key(event: dict) -> tuple:
    """Dated events first in date order, then recurring ones by weekday.

    A recurring event has no single date, which is exactly what
    `_event_sort_key` in `config/calendars.py` cannot represent -- it would
    compare None against a date string and raise. Hence a separate key here
    rather than reusing that one.
    """
    start = event.get("start") or ""
    first_weekday = (event.get("weekdays") or [7])[0]
    return (0 if start else 1, start, first_weekday,
            event.get("from", ""), event.get("kind", ""), event.get("label", ""))
