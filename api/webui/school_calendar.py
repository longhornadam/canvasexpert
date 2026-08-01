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
               "from", "to"}


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
        label = event.get("label")
        if not isinstance(label, str) or not label.strip():
            problems.append(f"{tag}: label must be a non-empty string")
        shape = event.get("shape")
        if shape not in EVENT_SHAPES:
            problems.append(f"{tag}: shape must be one of {sorted(EVENT_SHAPES)}")
            continue
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


def is_configured(root=None) -> bool:
    """True when a valid canonical document exists.

    School-day arithmetic callers (sweep, extensions, late catch-up, routines)
    must check this before trusting no_count_dates(): an unconfigured or
    invalid calendar returns an empty no-count set, which silently treats
    weekends as instructional days rather than refusing the operation.
    """
    doc, _problems = read(root)
    return doc is not None


def no_count_dates(date_from: str | None = None, date_to: str | None = None,
                   *, root=None) -> set[str]:
    """The dates in [date_from, date_to] that do not count as instructional.

    A date counts as no-count when its kind is no_school or
    no_regular_classes -- weekends included, since they are generated
    no_school days in the canonical document. Callers doing school-day
    lateness/due-date arithmetic (schooldays.py) use this instead of a
    skip_weekends flag plus a parallel holiday list: one calendar, one set.
    Omitting date_from/date_to returns the whole configured year's no-count
    set. An unconfigured or invalid calendar returns an empty set; the
    caller's own readiness gate is what should refuse the operation, not a
    guessed default.
    """
    doc, _problems = read(root)
    if doc is None:
        return set()
    start = date_from or doc["coverage"]["start"]
    end = date_to or doc["coverage"]["end"]
    return {
        date_key for date_key, entry in doc["days"].items()
        if start <= date_key <= end
        and entry.get("kind") in ("no_school", "no_regular_classes")
    }


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


def create_school_year(*, school_year, coverage_start, coverage_end, default_schedule_id,
                       weekday_schedules=None, no_school_dates=None,
                       no_regular_classes_dates=None, date_labels=None,
                       grading_periods=None, events=None, root=None) -> tuple[dict | None, list]:
    """Build and atomically write a complete school year. Revision starts at 1.

    Every calendar date in the requested coverage becomes an instructional
    weekday (using ``default_schedule_id`` or a matching ``weekday_schedules``
    override), a generated weekend, or an explicit no-school/no-regular-classes
    day -- there is no implied or missing date once this returns.
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

    no_school = set(no_school_dates or [])
    no_regular = set(no_regular_classes_dates or [])
    overlap = no_school & no_regular
    if overlap:
        return None, ["date(s) cannot be both no_school and no_regular_classes: "
                     + ", ".join(sorted(overlap)[:3])]
    labels = date_labels or {}

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

    payload = {
        "version": FORMAT_VERSION,
        "type": DOCUMENT_TYPE,
        "revision": 1,
        "school_year": school_year,
        "coverage": {"start": start.isoformat(), "end": end.isoformat()},
        "days": days,
        "grading_periods": grading_periods or [],
        "events": events or [],
    }
    parsed, problems = parse_document(payload)
    if problems:
        return None, problems

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
                   date_to=None, weekdays=None, root=None) -> tuple[dict | None, list[str]]:
    """Preview a day-kind/schedule/label change against the live document."""
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

    return {
        "base_revision": doc["revision"],
        "kind": kind,
        "affected": affected,
        "is_noop": all(entry["before"] == entry["after"] for entry in affected),
    }, []


def apply_change(preview: dict, *, expected_revision: int, root=None) -> tuple[dict | None, list[str]]:
    """Apply a previously returned preview. Refuses a stale expected_revision."""
    if not isinstance(preview, dict) or not isinstance(preview.get("affected"), list):
        return None, ["a valid preview is required"]

    doc, read_problems = read(root)
    if doc is None:
        return None, read_problems
    if doc["revision"] != expected_revision or preview.get("base_revision") != expected_revision:
        return None, [f"stale revision: expected {expected_revision}, "
                     f"calendar is at revision {doc['revision']}"]

    if preview.get("is_noop"):
        return doc, []

    next_days = dict(doc["days"])
    for entry in preview["affected"]:
        next_days[entry["date"]] = entry["after"]

    next_doc = {**doc, "days": next_days, "revision": doc["revision"] + 1}
    parsed, problems = parse_document(next_doc)
    if problems:
        return None, problems

    path = calendar_path(root)
    if not path:
        return None, ["no workspace available"]
    write_problems = _atomic_write(path, parsed)
    if write_problems:
        return None, write_problems
    return parsed, []
