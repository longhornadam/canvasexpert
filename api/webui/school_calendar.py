"""Canonical School Calendar service.

Single authority for school dates: one closed, versioned JSON document per
`docs/contracts/canonical-school-calendar-contract.md`. Every reader/writer in
the app and MCP server goes through this module; no consumer parses the file
or retains a second calendar projection.

Pure parsing/validation has no IO and no app imports at module level, matching
the posture of `deck_schedule.py`. IO (path resolution, atomic write) is kept
in the handful of functions that need it, with `workspace` imported lazily so
this module stays importable before a workspace exists.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import date, timedelta

FORMAT_VERSION = "1.0-json"
DOCUMENT_TYPE = "SCHOOL_CALENDAR"
CALENDAR_FILENAME = "School Calendar.json"

DAY_KINDS = frozenset({"instructional", "no_regular_classes", "no_school"})

# The closed, classroom-safe event vocabulary. Unchanged from the retired
# api/webui/school_events.py -- this domain absorbs that file's events array.
EVENT_KINDS = frozenset({
    "game", "dance", "assembly", "performance", "spirit",
    "tutorial", "club", "library", "other",
})
EVENT_SHAPES = frozenset({"date", "span", "weekdays"})

RESOLUTION_STATES = frozenset({
    "unconfigured", "invalid_calendar", "outside_coverage",
    "no_school", "no_regular_classes", "unknown_schedule", "ready",
})

WEEKEND_LABEL = "Weekend"

# A calendar within this many days of running out is a repair worth surfacing
# before it becomes an outage; see readiness().
LOW_COVERAGE_WARNING_DAYS = 30

_TOP_LEVEL_KEYS = {"version", "type", "revision", "school_year", "coverage",
                   "days", "grading_periods", "events"}
_DAY_KEYS = {"kind", "schedule_id", "label"}
_GRADING_PERIOD_KEYS = {"code", "name", "start", "end", "report_issue_date"}
_EVENT_KEYS = {"id", "kind", "label", "shape", "date", "start", "end",
               "weekdays", "effective_start", "effective_end", "detail",
               "from", "to", "result"}


# ----------------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------------

def calendar_path(root=None) -> str | None:
    """Where the canonical document lives, or None when there is no workspace."""
    from . import workspace
    folder = workspace.library_folder("Calendars", root) if root else workspace.library_folder("Calendars")
    return os.path.join(folder, CALENDAR_FILENAME) if folder else None


# ----------------------------------------------------------------------------
# Pure helpers
# ----------------------------------------------------------------------------

def _parse_date(value) -> date | None:
    """An exact ISO date, or None for anything untrusted or non-canonical."""
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == text else None


def _daterange(start: date, end: date):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def _normalize_weekday_map(weekday_schedules) -> tuple[dict, list]:
    if weekday_schedules is None:
        return {}, []
    if not isinstance(weekday_schedules, dict):
        return {}, ["weekday_schedules must be an object"]
    normalized = {}
    problems = []
    for raw_weekday, schedule_id in weekday_schedules.items():
        try:
            weekday = int(raw_weekday)
        except (TypeError, ValueError):
            problems.append(f"weekday_schedules key '{raw_weekday}' must be 0 through 4")
            continue
        if isinstance(raw_weekday, bool) or not (0 <= weekday <= 4):
            problems.append(f"weekday_schedules key '{raw_weekday}' must be 0 through 4")
            continue
        if not isinstance(schedule_id, str) or not schedule_id.strip():
            problems.append(f"weekday_schedules[{weekday}] must be a non-empty string")
            continue
        normalized[weekday] = schedule_id
    return normalized, problems


def _validate_day(date_key: str, entry) -> list[str]:
    if not isinstance(entry, dict):
        return [f"{date_key}: day entry must be an object"]
    problems = []
    extra = set(entry) - _DAY_KEYS
    if extra:
        problems.append(f"{date_key}: unknown day key(s): {', '.join(sorted(extra))}")
    kind = entry.get("kind")
    if kind not in DAY_KINDS:
        problems.append(f"{date_key}: kind must be one of {sorted(DAY_KINDS)}")
        return problems
    schedule_id = entry.get("schedule_id")
    label = entry.get("label")
    if label is not None and not isinstance(label, str):
        problems.append(f"{date_key}: label must be a string")
    if kind == "instructional":
        if not isinstance(schedule_id, str) or not schedule_id.strip():
            problems.append(f"{date_key}: instructional day requires a non-empty schedule_id")
        # An instructional day naming a schedule nobody has loaded is a
        # resolution-time "unknown_schedule" state, not a write-time failure --
        # a Bell Schedule may be added to the workspace after this write.
    else:
        if schedule_id is not None:
            problems.append(f"{date_key}: {kind} day must not name a schedule_id")
        if not isinstance(label, str) or not label.strip():
            problems.append(f"{date_key}: {kind} day requires a label")
    return problems


def _validate_grading_periods(periods, coverage_start: date, coverage_end: date) -> list[str]:
    if not isinstance(periods, list):
        return ["grading_periods must be a list"]
    problems = []
    codes_seen = set()
    parsed = []
    for index, period in enumerate(periods):
        tag = f"grading_periods[{index}]"
        if not isinstance(period, dict):
            problems.append(f"{tag} must be an object")
            continue
        extra = set(period) - _GRADING_PERIOD_KEYS
        if extra:
            problems.append(f"{tag}: unknown key(s): {', '.join(sorted(extra))}")
        code = period.get("code")
        if not isinstance(code, str) or not code.strip():
            problems.append(f"{tag}: code must be a non-empty string")
            continue
        tag = f"{tag} ('{code}')"
        if code in codes_seen:
            problems.append(f"{tag}: duplicate code")
        codes_seen.add(code)
        name = period.get("name")
        if not isinstance(name, str) or not name.strip():
            problems.append(f"{tag}: name must be a non-empty string")
        start = _parse_date(period.get("start"))
        end = _parse_date(period.get("end"))
        if not start or not end:
            problems.append(f"{tag}: start/end must be exact ISO dates")
            continue
        if start > end:
            problems.append(f"{tag}: start must not be after end")
            continue
        if start < coverage_start or end > coverage_end:
            problems.append(f"{tag}: start/end must be inside coverage")
        report_issue = period.get("report_issue_date")
        if report_issue is not None and not _parse_date(report_issue):
            problems.append(f"{tag}: report_issue_date must be an exact ISO date")
        parsed.append({"code": code, "start": start, "end": end})
    parsed.sort(key=lambda p: p["start"])
    for previous, current in zip(parsed, parsed[1:]):
        if current["start"] <= previous["end"]:
            problems.append(
                f"grading_periods overlap: '{previous['code']}' and '{current['code']}'")
    return problems


def _validate_events(events) -> list[str]:
    if not isinstance(events, list):
        return ["events must be a list"]
    problems = []
    ids_seen = set()
    for index, event in enumerate(events):
        tag = f"events[{index}]"
        if not isinstance(event, dict):
            problems.append(f"{tag} must be an object")
            continue
        extra = set(event) - _EVENT_KEYS
        if extra:
            problems.append(f"{tag}: unknown key(s): {', '.join(sorted(extra))}")
        event_id = event.get("id")
        if not isinstance(event_id, str) or not event_id.strip():
            problems.append(f"{tag}: id must be a non-empty string")
        elif event_id in ids_seen:
            problems.append(f"{tag} ('{event_id}'): duplicate id")
        else:
            ids_seen.add(event_id)
        tag = f"{tag} ('{event_id}')" if isinstance(event_id, str) else tag
        kind = event.get("kind")
        if kind not in EVENT_KINDS:
            problems.append(f"{tag}: kind must be one of {sorted(EVENT_KINDS)}")
        if "result" in event:
            if kind != "game":
                problems.append(f"{tag}: result is only valid for game events")
            elif not isinstance(event["result"], str):
                problems.append(f"{tag}: result must be a string")
            elif len(event["result"]) > 160:
                problems.append(f"{tag}: result must be 160 characters or fewer")
        label = event.get("label")
        if not isinstance(label, str) or not label.strip():
            problems.append(f"{tag}: label must be a non-empty string")
        shape = event.get("shape")
        if shape not in EVENT_SHAPES:
            problems.append(f"{tag}: shape must be one of {sorted(EVENT_SHAPES)}")
            continue
        shape_keys = {
            "date": {"date"},
            "span": {"start", "end"},
            "weekdays": {"weekdays", "effective_start", "effective_end"},
        }[shape]
        shape_fields = {"date", "start", "end", "weekdays", "effective_start", "effective_end"}
        unexpected_shape_fields = (set(event) & shape_fields) - shape_keys
        if unexpected_shape_fields:
            problems.append(f"{tag}: shape '{shape}' cannot include "
                            f"{', '.join(sorted(unexpected_shape_fields))}")
        if shape == "date":
            if not _parse_date(event.get("date")):
                problems.append(f"{tag}: date must be an exact ISO date")
        elif shape == "span":
            start = _parse_date(event.get("start"))
            end = _parse_date(event.get("end"))
            if not start or not end:
                problems.append(f"{tag}: start/end must be exact ISO dates")
            elif end < start:
                problems.append(f"{tag}: end must not be before start")
        elif shape == "weekdays":
            weekdays = event.get("weekdays")
            valid_weekdays = (
                isinstance(weekdays, list) and bool(weekdays)
                and all(isinstance(w, int) and not isinstance(w, bool) and 0 <= w <= 6
                        for w in weekdays)
            )
            if not valid_weekdays:
                problems.append(f"{tag}: weekdays must be a non-empty list of integers 0 through 6")
            for field in ("effective_start", "effective_end"):
                if event.get(field) is not None and not _parse_date(event.get(field)):
                    problems.append(f"{tag}: {field} must be an exact ISO date")
    return problems


def _event_touches_range(event: dict, date_from: date, date_to: date) -> bool:
    shape = event.get("shape")
    if shape == "date":
        found = _parse_date(event.get("date"))
        return bool(found and date_from <= found <= date_to)
    if shape == "span":
        start = _parse_date(event.get("start"))
        end = _parse_date(event.get("end"))
        return bool(start and end and not (end < date_from or start > date_to))
    if shape == "weekdays":
        weekdays = set(event.get("weekdays") or [])
        window_start = _parse_date(event.get("effective_start"))
        window_end = _parse_date(event.get("effective_end"))
        day = date_from
        while day <= date_to:
            if (day.weekday() in weekdays
                    and (not window_start or day >= window_start)
                    and (not window_end or day <= window_end)):
                return True
            day += timedelta(days=1)
        return False
    return False


def parse_document(payload) -> tuple[dict | None, list[str]]:
    """Validate a whole canonical document. Returns (parsed, problems).

    A document is either fully valid or rejected outright -- there is no
    partial acceptance, matching "unknown keys are rejected at every level".
    """
    if not isinstance(payload, dict):
        return None, ["document must be a JSON object"]

    problems = []
    extra = set(payload) - _TOP_LEVEL_KEYS
    if extra:
        problems.append(f"unknown top-level key(s): {', '.join(sorted(extra))}")

    if payload.get("version") != FORMAT_VERSION:
        problems.append(f"version must be '{FORMAT_VERSION}'")
    if payload.get("type") != DOCUMENT_TYPE:
        problems.append(f"type must be '{DOCUMENT_TYPE}'")

    revision = payload.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        problems.append("revision must be a positive integer")

    school_year = payload.get("school_year")
    if not isinstance(school_year, str) or not school_year.strip():
        problems.append("school_year must be a non-empty string")

    coverage = payload.get("coverage")
    coverage_start = coverage_end = None
    if not isinstance(coverage, dict) or set(coverage) - {"start", "end"}:
        problems.append("coverage must be an object with only start/end")
    else:
        coverage_start = _parse_date(coverage.get("start"))
        coverage_end = _parse_date(coverage.get("end"))
        if not coverage_start or not coverage_end:
            problems.append("coverage.start/end must be exact ISO dates")
        elif coverage_start > coverage_end:
            problems.append("coverage.start must not be after coverage.end")
            coverage_start = coverage_end = None

    days = payload.get("days")
    if not isinstance(days, dict):
        problems.append("days must be an object")
        days = {}

    day_problems = []
    for date_key, entry in days.items():
        if not _parse_date(date_key):
            day_problems.append(f"{date_key}: not an exact ISO date key")
            continue
        day_problems.extend(_validate_day(date_key, entry))
    problems.extend(day_problems)

    if coverage_start and coverage_end and not day_problems:
        expected = {day.isoformat() for day in _daterange(coverage_start, coverage_end)}
        actual = set(days)
        missing = sorted(expected - actual)
        outside = sorted(actual - expected)
        if missing:
            problems.append(
                f"days is missing {len(missing)} date(s) inside coverage, e.g. {missing[0]}")
        if outside:
            problems.append(
                f"days contains {len(outside)} date(s) outside coverage, e.g. {outside[0]}")

    if coverage_start and coverage_end:
        problems.extend(
            _validate_grading_periods(payload.get("grading_periods", []),
                                       coverage_start, coverage_end))
    problems.extend(_validate_events(payload.get("events", [])))

    if problems:
        return None, problems
    return payload, []


def resolve_date(doc: dict | None, date_str: str, known_schedule_ids) -> dict:
    """One resolution state for a single date. See contract section 4."""
    if doc is None:
        return {"state": "unconfigured", "date": date_str}
    coverage = doc.get("coverage") or {}
    start = _parse_date(coverage.get("start"))
    end = _parse_date(coverage.get("end"))
    target = _parse_date(date_str)
    entry = doc.get("days", {}).get(date_str) if isinstance(doc.get("days"), dict) else None
    if not start or not end or not target or target < start or target > end or not isinstance(entry, dict):
        return {"state": "outside_coverage", "date": date_str}

    kind = entry.get("kind")
    if kind == "no_school":
        return {"state": "no_school", "date": date_str, "label": entry.get("label")}
    if kind == "no_regular_classes":
        return {"state": "no_regular_classes", "date": date_str, "label": entry.get("label")}

    schedule_id = entry.get("schedule_id")
    if not schedule_id or schedule_id not in set(known_schedule_ids or ()):
        return {"state": "unknown_schedule", "date": date_str, "schedule_id": schedule_id}
    return {"state": "ready", "date": date_str, "schedule_id": schedule_id,
            "label": entry.get("label")}


def range_projection(date_from: str, date_to: str, *, root=None) -> tuple[dict | None, list[str]]:
    """A compact day/grading-period/event projection for one inclusive range."""
    doc, problems = read(root)
    if doc is None:
        return None, problems
    start = _parse_date(date_from)
    end = _parse_date(date_to)
    if not start or not end or start > end:
        return None, ["date_from/date_to must be exact ISO dates with date_from <= date_to"]
    days = {key: entry for key, entry in doc["days"].items() if date_from <= key <= date_to}
    periods = [p for p in doc["grading_periods"]
               if not (p["end"] < date_from or p["start"] > date_to)]
    events = [e for e in doc["events"] if _event_touches_range(e, start, end)]
    return {
        "revision": doc["revision"],
        "school_year": doc["school_year"],
        "days": days,
        "grading_periods": periods,
        "events": events,
    }, []


CALENDAR_REPAIR_MESSAGE = "Calendar needs attention. Open Calendar in Canvas Expert to set it up."
CALENDAR_REPAIR_TARGET = "/calendar"

_STATE_MESSAGES = {
    "unconfigured": CALENDAR_REPAIR_MESSAGE,
    "invalid_calendar": CALENDAR_REPAIR_MESSAGE,
    "outside_coverage": CALENDAR_REPAIR_MESSAGE,
    "unknown_schedule": CALENDAR_REPAIR_MESSAGE,
    "no_school": "No school today.",
    "no_regular_classes": "No regular classes today.",
}


def state_message(state: str) -> str | None:
    """A teacher-facing message for a non-ready resolve_date()/
    resolve_schedule_for() state, or None for "ready" (nothing to report).
    Named day states (no_school/no_regular_classes) get their own message
    rather than collapsing into the generic Calendar repair message."""
    return _STATE_MESSAGES.get(state)


def _repair_failure(state: str, problems: list[str]) -> dict:
    return {"state": state, "problems": problems, "repair_url": CALENDAR_REPAIR_TARGET}


def _document_or_failure(root) -> tuple[dict | None, dict | None]:
    """(doc, None) for a valid canonical document, else (None, failure_dict).

    Shared entry point for every checked seam below: a consumer doing
    instructional-day arithmetic must fail closed on unconfigured/invalid
    calendar state rather than silently treating an empty no-count set as
    "no exceptional days" (which would count weekends as instructional).
    """
    doc, problems = read(root)
    if doc is None:
        state = problems[0] if problems and problems[0] in ("unconfigured", "invalid_calendar") else "unconfigured"
        return None, _repair_failure(state, problems)
    return doc, None


def resolve_instructional_range(date_from: str, date_to: str, known_schedule_ids,
                                *, root=None) -> dict:
    """A checked day/no-count projection for one inclusive range.

    Success: {state: "ready", date_from, date_to, days, no_count_dates}.
    Failure uses the canonical state (unconfigured, invalid_calendar,
    outside_coverage, or unknown_schedule), concrete problems, and the shared
    /calendar repair target. A date outside coverage, or an instructional
    date naming a Bell Schedule not in known_schedule_ids, fails the WHOLE
    request -- this never returns a clipped/partial success.
    """
    doc, failure = _document_or_failure(root)
    if doc is None:
        return failure
    start = _parse_date(date_from)
    end = _parse_date(date_to)
    if not start or not end or start > end:
        return _repair_failure(
            "invalid_calendar",
            ["date_from/date_to must be exact ISO dates with date_from <= date_to"])

    coverage = doc["coverage"]
    if date_from < coverage["start"] or date_to > coverage["end"]:
        return _repair_failure(
            "outside_coverage",
            [f"requested range {date_from}..{date_to} is not wholly inside "
             f"coverage {coverage['start']}..{coverage['end']}"])

    known = set(known_schedule_ids or ())
    days = {}
    no_count = []
    unknown = []
    for day in _daterange(start, end):
        key = day.isoformat()
        entry = doc["days"].get(key)
        if not isinstance(entry, dict):
            return _repair_failure("invalid_calendar", [f"{key}: missing day entry"])
        days[key] = entry
        kind = entry.get("kind")
        if kind in ("no_school", "no_regular_classes"):
            no_count.append(key)
        elif kind == "instructional" and entry.get("schedule_id") not in known:
            unknown.append(key)
    if unknown:
        return _repair_failure(
            "unknown_schedule",
            [f"{key}: instructional day names a Bell Schedule that is not currently loaded"
             for key in unknown[:3]])

    return {"state": "ready", "date_from": date_from, "date_to": date_to,
            "days": days, "no_count_dates": no_count}


def add_school_days_checked(start_dt, days: int, known_schedule_ids, *, root=None):
    """Add N instructional days to ``start_dt``.

    Returns (result_datetime, None) on success, or (None, failure_dict) when
    coverage ends before the calculation can complete, ``start_dt`` itself is
    outside coverage, or an instructional day the walk must inspect names a
    Bell Schedule that is not currently loaded. Never silently walks past the
    known calendar (e.g. treating the day after coverage's last Friday as an
    ordinary school day).
    """
    doc, failure = _document_or_failure(root)
    if doc is None:
        return None, failure
    coverage = doc["coverage"]
    known = set(known_schedule_ids or ())
    start_key = start_dt.date().isoformat()
    if start_key < coverage["start"] or start_key > coverage["end"]:
        return None, _repair_failure(
            "outside_coverage",
            [f"{start_key} is outside coverage {coverage['start']}..{coverage['end']}"])

    cursor = start_dt
    added = 0
    while added < days:
        cursor = cursor + timedelta(days=1)
        key = cursor.date().isoformat()
        if key > coverage["end"]:
            return None, _repair_failure(
                "outside_coverage",
                [f"coverage ends {coverage['end']}, before {days} school day(s) "
                 f"from {start_key} can be counted"])
        resolution = resolve_date(doc, key, known)
        if resolution["state"] == "unknown_schedule":
            return None, _repair_failure(
                "unknown_schedule",
                [f"{key}: instructional day names a Bell Schedule that is not currently loaded"])
        if resolution["state"] not in ("no_school", "no_regular_classes"):
            added += 1
    return cursor, None


def count_school_days_checked(due_dt, submitted_dt, known_schedule_ids, *, root=None):
    """School days in (due_dt, submitted_dt] as (count, None), or (None,
    failure_dict) on the same fail-closed terms as add_school_days_checked."""
    doc, failure = _document_or_failure(root)
    if doc is None:
        return None, failure
    coverage = doc["coverage"]
    known = set(known_schedule_ids or ())
    due_key = due_dt.date().isoformat()
    if due_key < coverage["start"] or due_key > coverage["end"]:
        return None, _repair_failure(
            "outside_coverage",
            [f"{due_key} is outside coverage {coverage['start']}..{coverage['end']}"])
    if submitted_dt.date() <= due_dt.date():
        return 0, None

    cursor = due_dt
    count = 0
    while cursor.date() < submitted_dt.date():
        cursor = cursor + timedelta(days=1)
        key = cursor.date().isoformat()
        if key > coverage["end"]:
            return None, _repair_failure(
                "outside_coverage",
                [f"coverage ends {coverage['end']}, before lateness through "
                 f"{submitted_dt.date().isoformat()} can be counted"])
        resolution = resolve_date(doc, key, known)
        if resolution["state"] == "unknown_schedule":
            return None, _repair_failure(
                "unknown_schedule",
                [f"{key}: instructional day names a Bell Schedule that is not currently loaded"])
        if resolution["state"] not in ("no_school", "no_regular_classes"):
            count += 1
    return count, None


def readiness(*, bell_schedule_ids=None, today: str | None = None, root=None) -> dict:
    """Overall calendar health, independent of any one date's resolution."""
    known = set(bell_schedule_ids or ())
    doc, problems = read(root)
    if doc is None:
        status = problems[0] if problems and problems[0] in ("unconfigured", "invalid_calendar") else "unconfigured"
        return {"status": status, "problems": problems}

    today_str = today or date.today().isoformat()
    today_state = resolve_date(doc, today_str, known)

    coverage_end = _parse_date(doc["coverage"]["end"])
    today_parsed = _parse_date(today_str)
    remaining_days = (coverage_end - today_parsed).days if coverage_end and today_parsed else None

    unknown_schedule_dates = sorted(
        date_key for date_key, entry in doc["days"].items()
        if entry.get("kind") == "instructional" and entry.get("schedule_id") not in known
    )

    needs_attention = (
        today_state["state"] == "outside_coverage"
        or bool(unknown_schedule_dates)
        or (remaining_days is not None and remaining_days < LOW_COVERAGE_WARNING_DAYS)
    )

    return {
        "status": "needs_attention" if needs_attention else "ready",
        "revision": doc["revision"],
        "school_year": doc["school_year"],
        "coverage": doc["coverage"],
        "today": today_state,
        "remaining_coverage_days": remaining_days,
        "unknown_schedule_dates": unknown_schedule_dates,
    }


# ----------------------------------------------------------------------------
# IO
# ----------------------------------------------------------------------------

def read(root=None) -> tuple[dict | None, list[str]]:
    """The current document, parsed and validated, or (None, problems)."""
    path = calendar_path(root)
    if not path or not os.path.isfile(path):
        return None, ["unconfigured"]
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError) as exc:
        return None, [f"could not read {CALENDAR_FILENAME}: {exc}"]
    parsed, problems = parse_document(payload)
    if parsed is None:
        return None, (["invalid_calendar"] + problems)
    return parsed, []


def _atomic_write(path: str, payload: dict) -> list[str]:
    folder = os.path.dirname(path)
    fd = None
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(
            prefix=".school_calendar_", suffix=".partial", dir=folder, text=True)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except (OSError, IOError) as exc:
        if temporary and os.path.exists(temporary):
            try:
                os.unlink(temporary)
            except OSError:
                pass
        return [f"failed to write {CALENDAR_FILENAME}: {exc}"]
    return []


def _normalize_replacement_mutation(*, school_year, coverage_start, coverage_end,
                                    default_schedule_id, weekday_schedules=None,
                                    no_school_dates=None, no_regular_classes_dates=None,
                                    date_labels=None, grading_periods=None,
                                    events=None) -> tuple[dict | None, list]:
    """Validate and normalize raw create/replace inputs into a stable,
    JSON-serializable mutation dict: sorted lists/dicts so two equivalent
    requests (same content, different client-side ordering) digest the same.
    """
    start = _parse_date(coverage_start)
    end = _parse_date(coverage_end)
    if not start or not end:
        return None, ["coverage_start/coverage_end must be exact ISO dates"]
    if start > end:
        return None, ["coverage_start must not be after coverage_end"]
    if not isinstance(default_schedule_id, str) or not default_schedule_id.strip():
        return None, ["default_schedule_id must be a non-empty string"]
    if not isinstance(school_year, str) or not school_year.strip():
        return None, ["school_year must be a non-empty string"]

    weekday_map, problems = _normalize_weekday_map(weekday_schedules)
    if problems:
        return None, problems

    no_school = sorted(set(no_school_dates or []))
    no_regular = sorted(set(no_regular_classes_dates or []))
    overlap = set(no_school) & set(no_regular)
    if overlap:
        return None, ["date(s) cannot be both no_school and no_regular_classes: "
                     + ", ".join(sorted(overlap)[:3])]

    return {
        "school_year": school_year,
        "coverage_start": start.isoformat(),
        "coverage_end": end.isoformat(),
        "default_schedule_id": default_schedule_id,
        "weekday_schedules": {str(weekday): schedule_id
                             for weekday, schedule_id in sorted(weekday_map.items())},
        "no_school_dates": no_school,
        "no_regular_classes_dates": no_regular,
        "date_labels": dict(sorted((date_labels or {}).items())),
        "grading_periods": grading_periods or [],
        "events": events or [],
    }, []


def _build_replacement_document(mutation: dict, *, revision: int) -> dict:
    """The complete candidate document for a normalized replacement mutation.

    Every calendar date in coverage becomes an instructional weekday (using
    ``default_schedule_id`` or a matching ``weekday_schedules`` override), a
    generated weekend, or an explicit no-school/no-regular-classes day --
    there is no implied or missing date once this returns. Not validated or
    written here; callers run this through parse_document and the write path.
    """
    start = _parse_date(mutation["coverage_start"])
    end = _parse_date(mutation["coverage_end"])
    weekday_map = {int(weekday): schedule_id
                  for weekday, schedule_id in mutation["weekday_schedules"].items()}
    no_school = set(mutation["no_school_dates"])
    no_regular = set(mutation["no_regular_classes_dates"])
    labels = mutation["date_labels"]
    default_schedule_id = mutation["default_schedule_id"]

    days = {}
    for day in _daterange(start, end):
        key = day.isoformat()
        if key in no_school:
            days[key] = {"kind": "no_school", "schedule_id": None,
                        "label": labels.get(key, "No school")}
        elif key in no_regular:
            days[key] = {"kind": "no_regular_classes", "schedule_id": None,
                        "label": labels.get(key, "No regular classes")}
        elif day.weekday() >= 5:
            days[key] = {"kind": "no_school", "schedule_id": None, "label": WEEKEND_LABEL}
        else:
            days[key] = {"kind": "instructional",
                        "schedule_id": weekday_map.get(day.weekday(), default_schedule_id)}

    return {
        "version": FORMAT_VERSION,
        "type": DOCUMENT_TYPE,
        "revision": revision,
        "school_year": mutation["school_year"],
        "coverage": {"start": start.isoformat(), "end": end.isoformat()},
        "days": days,
        "grading_periods": mutation["grading_periods"],
        "events": mutation["events"],
    }


def _validate_known_schedules(days: dict, known_schedule_ids) -> list[str]:
    """Write-time companion to resolve_date's read-time unknown_schedule
    state: a create/replace/date write rejects an instructional date naming
    a Bell Schedule that is not currently loaded, rather than accepting it
    silently and only discovering the problem the next time the date resolves.
    """
    known = set(known_schedule_ids or ())
    unknown = sorted(
        key for key, entry in days.items()
        if isinstance(entry, dict) and entry.get("kind") == "instructional"
        and entry.get("schedule_id") not in known
    )
    if not unknown:
        return []
    sample = ", ".join(unknown[:3])
    return [f"{len(unknown)} instructional date(s) name a Bell Schedule that is not "
            f"currently loaded, e.g. {sample}"]


def _diff_days(before: dict, after: dict) -> dict:
    """Material day-level change counts between two ``days`` dicts, for a
    replacement preview's teacher-facing summary."""
    before_keys, after_keys = set(before), set(after)
    changed = {key for key in (before_keys & after_keys) if before[key] != after[key]}
    return {
        "days_added": len(after_keys - before_keys),
        "days_removed": len(before_keys - after_keys),
        "days_changed": len(changed),
    }


def _digest_for_mutation(operation: str, base_revision: int, mutation: dict) -> str:
    """Deterministic digest over an operation's normalized mutation input.

    A local correctness boundary against a stale or accidentally altered
    preview payload (a UI bug, or fields from two different previews mixed
    together) -- not an authentication mechanism, since apply recomputes this
    from the same client-echoed mutation it verifies against.
    """
    payload = json.dumps({"operation": operation, "base_revision": base_revision,
                          "mutation": mutation},
                         sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_document(parsed: dict, root) -> tuple[dict | None, list]:
    path = calendar_path(root)
    if not path:
        return None, ["no workspace available"]
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError as exc:
        return None, [f"could not create Calendars folder: {exc}"]
    write_problems = _atomic_write(path, parsed)
    if write_problems:
        return None, write_problems
    return parsed, []


def create_school_year(*, school_year, coverage_start, coverage_end, default_schedule_id,
                       weekday_schedules=None, no_school_dates=None,
                       no_regular_classes_dates=None, date_labels=None,
                       grading_periods=None, events=None, root=None) -> tuple[dict | None, list]:
    """Build and atomically write a complete school year directly, bypassing
    preview/apply. Revision is current+1 (1 for a first write) and never
    resets, even when replacing an existing document.

    This is a test/internal convenience seam only -- no route or MCP tool
    calls it directly. Production create/replace goes through
    preview_replacement/apply_replacement, which additionally stage a
    teacher-facing preview and reject an unknown Bell Schedule at write time.
    """
    mutation, problems = _normalize_replacement_mutation(
        school_year=school_year, coverage_start=coverage_start, coverage_end=coverage_end,
        default_schedule_id=default_schedule_id, weekday_schedules=weekday_schedules,
        no_school_dates=no_school_dates, no_regular_classes_dates=no_regular_classes_dates,
        date_labels=date_labels, grading_periods=grading_periods, events=events)
    if problems:
        return None, problems

    current_doc, _current_problems = read(root)
    base_revision = current_doc["revision"] if current_doc else 0

    candidate = _build_replacement_document(mutation, revision=base_revision + 1)
    parsed, problems = parse_document(candidate)
    if problems:
        return None, problems
    return _write_document(parsed, root)


def preview_replacement(*, school_year, coverage_start, coverage_end, default_schedule_id,
                        weekday_schedules=None, no_school_dates=None,
                        no_regular_classes_dates=None, date_labels=None,
                        grading_periods=None, events=None, known_schedule_ids,
                        root=None) -> tuple[dict | None, list]:
    """Preview a complete school-year create/replace. Never writes.

    Returns a staged preview with ``operation`` ("create" when no document
    exists yet, else "replace"), ``base_revision``, the normalized
    ``mutation``, current/proposed school year and coverage, day/grading-
    period/event counts, ``material_changes``, ``conflicts``, and a
    ``preview_digest``. Rejects an instructional date naming a Bell Schedule
    outside ``known_schedule_ids`` here, at write time, rather than only at
    later resolution.
    """
    mutation, problems = _normalize_replacement_mutation(
        school_year=school_year, coverage_start=coverage_start, coverage_end=coverage_end,
        default_schedule_id=default_schedule_id, weekday_schedules=weekday_schedules,
        no_school_dates=no_school_dates, no_regular_classes_dates=no_regular_classes_dates,
        date_labels=date_labels, grading_periods=grading_periods, events=events)
    if problems:
        return None, problems

    current_doc, _current_problems = read(root)
    base_revision = current_doc["revision"] if current_doc else 0
    operation = "replace" if current_doc else "create"

    candidate = _build_replacement_document(mutation, revision=base_revision + 1)
    parsed, problems = parse_document(candidate)
    if problems:
        return None, problems
    schedule_problems = _validate_known_schedules(parsed["days"], known_schedule_ids)
    if schedule_problems:
        return None, schedule_problems

    preview = {
        "operation": operation,
        "base_revision": base_revision,
        "mutation": mutation,
        "current_school_year": current_doc["school_year"] if current_doc else None,
        "current_coverage": current_doc["coverage"] if current_doc else None,
        "proposed_school_year": parsed["school_year"],
        "proposed_coverage": parsed["coverage"],
        "day_count": len(parsed["days"]),
        "grading_period_count": len(parsed["grading_periods"]),
        "event_count": len(parsed["events"]),
        "material_changes": _diff_days(current_doc["days"] if current_doc else {}, parsed["days"]),
        "conflicts": [],
    }
    preview["preview_digest"] = _digest_for_mutation(operation, base_revision, mutation)
    return preview, []


def apply_replacement(preview: dict, *, expected_revision: int, root=None) -> tuple[dict | None, list]:
    """Apply a previously returned replacement preview.

    Re-derives the candidate document from the preview's own normalized
    ``mutation`` -- never from a client-supplied document -- and refuses a
    stale ``expected_revision`` or a preview whose digest no longer matches
    its own mutation.
    """
    if not isinstance(preview, dict) or not isinstance(preview.get("mutation"), dict):
        return None, ["a valid preview is required"]
    operation = preview.get("operation")
    if operation not in ("create", "replace"):
        return None, ["a valid preview is required"]
    mutation = preview["mutation"]

    current_doc, _current_problems = read(root)
    current_revision = current_doc["revision"] if current_doc else 0
    if current_revision != expected_revision or preview.get("base_revision") != expected_revision:
        return None, [f"stale revision: expected {expected_revision}, "
                     f"calendar is at revision {current_revision}"]

    expected_digest = _digest_for_mutation(operation, expected_revision, mutation)
    if preview.get("preview_digest") != expected_digest:
        return None, ["stale or altered preview: digest mismatch"]

    candidate = _build_replacement_document(mutation, revision=expected_revision + 1)
    parsed, problems = parse_document(candidate)
    if problems:
        return None, problems
    return _write_document(parsed, root)


def _resolve_target_dates(*, dates=None, date_from=None, date_to=None,
                          weekdays=None) -> tuple[list[str] | None, list[str]]:
    """Materialize the exact dates a change targets.

    Exactly one of an explicit ``dates`` list or a ``date_from``/``date_to``
    range (with an optional ``weekdays`` subset) may be given.
    """
    if dates is not None and (date_from is not None or date_to is not None):
        return None, ["provide either an explicit date list or a date range, not both"]

    if dates is not None:
        if not isinstance(dates, list) or not dates:
            return None, ["dates must be a non-empty list"]
        parsed = []
        for value in dates:
            parsed_date = _parse_date(value)
            if not parsed_date:
                return None, [f"invalid date: {value}"]
            parsed.append(parsed_date)
        return sorted({day.isoformat() for day in parsed}), []

    if date_from is None or date_to is None:
        return None, ["provide dates, or both date_from and date_to"]
    start = _parse_date(date_from)
    end = _parse_date(date_to)
    if not start or not end:
        return None, ["date_from/date_to must be exact ISO dates"]
    if start > end:
        return None, ["date_from must not be after date_to"]

    weekday_subset = None
    if weekdays is not None:
        valid = (isinstance(weekdays, list)
                 and all(isinstance(w, int) and not isinstance(w, bool) and 0 <= w <= 6
                        for w in weekdays))
        if not valid:
            return None, ["weekdays must be a list of integers 0 through 6"]
        weekday_subset = set(weekdays)

    result = [day.isoformat() for day in _daterange(start, end)
             if weekday_subset is None or day.weekday() in weekday_subset]
    if not result:
        return None, ["the requested range selects no dates"]
    return result, []


def preview_change(*, kind, schedule_id=None, label=None, dates=None, date_from=None,
                   date_to=None, weekdays=None, known_schedule_ids,
                   root=None) -> tuple[dict | None, list[str]]:
    """Preview a day-kind/schedule/label change against the live document.

    Rejects an instructional new value naming a Bell Schedule outside
    ``known_schedule_ids`` here, at write time. The returned preview carries
    a normalized ``mutation`` (kind/entry/dates) and a ``preview_digest``;
    ``affected`` is display-only -- apply never trusts it as write authority.
    """
    if kind not in DAY_KINDS:
        return None, [f"kind must be one of {sorted(DAY_KINDS)}"]

    target_dates, problems = _resolve_target_dates(
        dates=dates, date_from=date_from, date_to=date_to, weekdays=weekdays)
    if problems:
        return None, problems

    doc, read_problems = read(root)
    if doc is None:
        return None, read_problems

    coverage = doc["coverage"]
    out_of_coverage = [d for d in target_dates if d < coverage["start"] or d > coverage["end"]]
    if out_of_coverage:
        return None, ["date(s) outside coverage: " + ", ".join(out_of_coverage[:3])]

    new_entry = {"kind": kind}
    if kind == "instructional":
        if not isinstance(schedule_id, str) or not schedule_id.strip():
            return None, ["instructional day requires schedule_id"]
        if schedule_id not in set(known_schedule_ids or ()):
            return None, [f"schedule_id '{schedule_id}' is not a currently loaded Bell Schedule"]
        new_entry["schedule_id"] = schedule_id
        if label is not None:
            if not isinstance(label, str):
                return None, ["label must be a string"]
            new_entry["label"] = label
    else:
        if schedule_id is not None:
            return None, [f"{kind} day must not name a schedule_id"]
        if not isinstance(label, str) or not label.strip():
            return None, [f"{kind} day requires a label"]
        new_entry["schedule_id"] = None
        new_entry["label"] = label

    affected = []
    for date_key in target_dates:
        before = doc["days"].get(date_key)
        affected.append({"date": date_key, "before": before, "after": dict(new_entry)})

    mutation = {"kind": kind, "entry": new_entry, "dates": target_dates}
    preview = {
        "operation": "date_change",
        "base_revision": doc["revision"],
        "kind": kind,
        "mutation": mutation,
        "affected": affected,
        "is_noop": all(entry["before"] == entry["after"] for entry in affected),
        "conflicts": [],
    }
    preview["preview_digest"] = _digest_for_mutation("date_change", doc["revision"], mutation)
    return preview, []


def apply_change(preview: dict, *, expected_revision: int, root=None) -> tuple[dict | None, list[str]]:
    """Apply a previously returned preview. Refuses a stale expected_revision
    or a preview whose digest no longer matches its own mutation.

    Re-derives the write purely from the preview's normalized ``mutation`` --
    a client-edited ``affected``/``before``/``after`` row is never write
    authority.
    """
    if not isinstance(preview, dict):
        return None, ["a valid preview is required"]
    mutation = preview.get("mutation")
    if (not isinstance(mutation, dict) or not isinstance(mutation.get("dates"), list)
            or not isinstance(mutation.get("entry"), dict)):
        return None, ["a valid preview is required"]

    doc, read_problems = read(root)
    if doc is None:
        return None, read_problems
    if doc["revision"] != expected_revision or preview.get("base_revision") != expected_revision:
        return None, [f"stale revision: expected {expected_revision}, "
                     f"calendar is at revision {doc['revision']}"]

    expected_digest = _digest_for_mutation("date_change", expected_revision, mutation)
    if preview.get("preview_digest") != expected_digest:
        return None, ["stale or altered preview: digest mismatch"]

    entry = mutation["entry"]
    dates = mutation["dates"]
    if all(doc["days"].get(date_key) == entry for date_key in dates):
        return doc, []

    next_days = dict(doc["days"])
    for date_key in dates:
        next_days[date_key] = dict(entry)

    next_doc = {**doc, "days": next_days, "revision": doc["revision"] + 1}
    parsed, problems = parse_document(next_doc)
    if problems:
        return None, problems
    return _write_document(parsed, root)


# ----------------------------------------------------------------------------
# Public event mutation (preview/apply)
# ----------------------------------------------------------------------------

def _normalize_event(event) -> tuple[dict | None, list[str]]:
    """Validate one public event and return its stable JSON shape."""
    problems = _validate_events([event])
    if problems:
        return None, problems
    normalized = {key: event[key] for key in _EVENT_KEYS if key in event}
    if normalized.get("shape") == "weekdays":
        normalized["weekdays"] = sorted(set(normalized["weekdays"]))
    return normalized, []


def _normalize_event_mutation(*, action, event=None, event_id=None) -> tuple[dict | None, list[str]]:
    """Normalize the small event mutation grammar shared by UI and MCP."""
    if action not in ("upsert", "delete"):
        return None, ["action must be 'upsert' or 'delete'"]
    if action == "upsert":
        if event_id not in (None, ""):
            return None, ["event_id is only used for delete; use event.id for upsert"]
        normalized, problems = _normalize_event(event)
        if problems:
            return None, problems
        return {"action": "upsert", "event": normalized}, []
    if event is not None:
        return None, ["delete does not accept an event object"]
    if not isinstance(event_id, str) or not event_id.strip():
        return None, ["delete requires a non-empty event_id"]
    return {"action": "delete", "event_id": event_id}, []


def _event_after_mutation(events: list, mutation: dict) -> tuple[dict | None, list]:
    """Return the event list after applying a normalized mutation in memory."""
    next_events = [dict(event) for event in events]
    if mutation["action"] == "delete":
        next_events = [event for event in next_events if event.get("id") != mutation["event_id"]]
        return next_events, []

    replacement = mutation["event"]
    found = False
    for index, event in enumerate(next_events):
        if event.get("id") == replacement["id"]:
            next_events[index] = dict(replacement)
            found = True
            break
    if not found:
        next_events.append(dict(replacement))
    return next_events, []


def preview_event_change(*, action, event=None, event_id=None, root=None) -> tuple[dict | None, list[str]]:
    """Preview an upsert or delete in the canonical public ``events`` array.

    The before/after values are display projections. Apply verifies them again
    against the current document, while deriving its write from ``mutation``.
    """
    mutation, problems = _normalize_event_mutation(
        action=action, event=event, event_id=event_id)
    if problems:
        return None, problems
    doc, read_problems = read(root)
    if doc is None:
        return None, read_problems

    target_id = mutation.get("event_id") or mutation["event"].get("id")
    before = next((dict(item) for item in doc["events"] if item.get("id") == target_id), None)
    after = dict(mutation["event"]) if mutation["action"] == "upsert" else None
    preview = {
        "operation": "event_change",
        "base_revision": doc["revision"],
        "mutation": mutation,
        "before": before,
        "after": after,
        "conflicts": [],
        "is_noop": before == after,
    }
    preview["preview_digest"] = _digest_for_mutation(
        "event_change", doc["revision"], mutation)
    return preview, []


def apply_event_change(preview: dict, *, expected_revision: int, root=None) -> tuple[dict | None, list[str]]:
    """Apply a checked event preview through whole-document validation/write."""
    if not isinstance(preview, dict) or preview.get("operation") != "event_change":
        return None, ["a valid event preview is required"]
    raw_mutation = preview.get("mutation")
    if not isinstance(raw_mutation, dict):
        return None, ["a valid event preview is required"]
    action = raw_mutation.get("action")
    if action == "upsert":
        mutation, problems = _normalize_event_mutation(
            action=action, event=raw_mutation.get("event"))
    elif action == "delete":
        mutation, problems = _normalize_event_mutation(
            action=action, event_id=raw_mutation.get("event_id"))
    else:
        return None, ["a valid event preview is required"]
    if problems or mutation != raw_mutation:
        return None, problems or ["event preview mutation is not normalized"]

    doc, read_problems = read(root)
    if doc is None:
        return None, read_problems
    if doc["revision"] != expected_revision or preview.get("base_revision") != expected_revision:
        return None, [f"stale revision: expected {expected_revision}, "
                      f"calendar is at revision {doc['revision']}"]
    expected_digest = _digest_for_mutation("event_change", expected_revision, mutation)
    if preview.get("preview_digest") != expected_digest:
        return None, ["stale or altered preview: digest mismatch"]

    target_id = mutation.get("event_id") or mutation["event"].get("id")
    before = next((dict(item) for item in doc["events"] if item.get("id") == target_id), None)
    after = dict(mutation["event"]) if action == "upsert" else None
    if preview.get("before") != before or preview.get("after") != after:
        return None, ["stale or altered preview: before/after projection mismatch"]

    next_events, _ = _event_after_mutation(doc["events"], mutation)
    if next_events == doc["events"]:
        return doc, []
    next_doc = {**doc, "events": next_events, "revision": doc["revision"] + 1}
    parsed, problems = parse_document(next_doc)
    if problems:
        return None, problems
    return _write_document(parsed, root)
