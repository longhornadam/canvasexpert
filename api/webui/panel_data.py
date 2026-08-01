"""Pure data projections for the public Calendar Panels.

The route module owns URLs and course/schedule resolution.  This module owns
the small, disk-read seams and the classroom-facing projections that turn the
canonical School Calendar into panel payloads.  Every public payload is calm:
it returns ``ok`` and a named state with empty collections when a local source
is unavailable or malformed.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
import json

from api import audience, learning_objectives
from api.mirror import read_service
from api.course_catalog import read_catalog
from api.webui import config, deps, school_calendar


DEFAULT_DUE_DAYS = 7
MAX_DUE_DAYS = 31
DEFAULT_UPCOMING_DAYS = 14
MAX_UPCOMING_DAYS = 60
DEFAULT_SPORTS_DAYS = 14
MAX_SPORTS_DAYS = 90
DEFAULT_BIRTHDAY_DAYS = 7
MAX_BIRTHDAY_DAYS = 31

_SYNC_MESSAGE = "Sync now in Canvas Expert to show this panel."
_PRIVATE_SCOPE_NAMES = {
    read_service.PRIVATE_ROSTER,
    read_service.PRIVATE_ASSIGNMENTS,
    read_service.PRIVATE_SUBMISSIONS,
}

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


def learning_objective_payload(course_id: str, *, now=None, catalog_reader=None,
                               document_reader=None) -> dict:
    """Render one reviewed objective from disk and current local evidence."""
    if not course_id:
        return {"ok": True, "state": "no_course", "objective": "",
                "message": "Choose a course for this panel."}
    reader = document_reader or learning_objectives.read_document
    try:
        document = reader()
        learning_objectives.validate_document(document)
    except Exception:
        return {"ok": True, "state": "catalog_needs_attention", "objective": "",
                "message": "Learning Objectives needs attention. Repair the local document in Canvas Expert."}
    entries = (document.get("objectives", {}).get(str(course_id), [])
               if isinstance(document, dict) else [])
    if not isinstance(entries, list):
        return {"ok": True, "state": "catalog_needs_attention", "objective": "",
                "message": "Catalog needs attention. Refresh it in Canvas Expert."}
    today = _local_date(now).isoformat()
    covering = [entry for entry in entries
                if isinstance(entry, dict)
                and str(entry.get("effective_start")) <= today <= str(entry.get("effective_end"))]
    if not covering:
        expired = any(isinstance(entry, dict) and str(entry.get("effective_end")) < today
                      for entry in entries)
        state = "expired" if expired else "no_objective"
        message = ("This learning objective has expired." if expired else
                   "No learning objective is scheduled for today.")
        return {"ok": True, "state": state, "objective": "", "message": message}
    if len(covering) != 1:
        return {"ok": True, "state": "catalog_needs_attention", "objective": "",
                "message": "Catalog needs attention. Refresh it in Canvas Expert."}
    reader = catalog_reader or (lambda cid: read_catalog(cid))
    try:
        read_result = reader(course_id)
        catalog = read_result.get("catalog") if isinstance(read_result, dict) else None
        if not isinstance(catalog, dict) or catalog.get("version") != 3:
            return {"ok": True, "state": "catalog_needs_attention", "objective": "",
                    "message": "Catalog needs attention. Refresh it in Canvas Expert."}
        entry = learning_objectives.normalize_entry(covering[0])
        if learning_objectives.source_digest(catalog, entry["source_refs"]) != entry["source_digest"]:
            raise ValueError("source changed")
    except Exception:
        return {"ok": True, "state": "changed_source", "objective": "",
                "message": "Objective needs review."}
    fact = audience.tag({"kind": "learning_objective", "text": entry["objective"]})
    safe = audience.classroom_only([fact])
    if not safe:
        return {"ok": True, "state": "catalog_needs_attention", "objective": "",
                "message": "Catalog needs attention. Refresh it in Canvas Expert."}
    return {
        "ok": True,
        "state": "ready",
        "objective": safe[0]["text"],
        "kind": safe[0]["kind"],
        "course_name": str(catalog.get("course_name") or ""),
        "message": "",
    }


# ---------------------------------------------------------------------------
# Current-course roster-backed Panels
# ---------------------------------------------------------------------------

def _private_scope(course_id: str, scope: str, *, mirror_root=None,
                   scope_reader=None) -> dict | None:
    """Read one typed, local-display Mirror scope without a fallback."""
    if scope not in _PRIVATE_SCOPE_NAMES:
        return None
    try:
        if scope_reader is not None:
            try:
                result = scope_reader(scope, course_id,
                                      intent=read_service.LOCAL_DISPLAY,
                                      root=mirror_root)
            except TypeError:
                result = scope_reader(scope, course_id)
        else:
            result = read_service.read(scope, course_id,
                                       intent=read_service.LOCAL_DISPLAY,
                                       root=mirror_root)
    except Exception:
        return None
    return result if isinstance(result, dict) else None


def _current_scope(result: dict | None, course_id: str, scope: str) -> bool:
    return bool(
        isinstance(result, dict)
        and result.get("course_id") == str(course_id)
        and result.get("scope") == scope
        and result.get("state") == "current"
        and result.get("capability") == "supported"
        and result.get("source") == "mirror"
        and isinstance(result.get("records"), list)
    )


def _attention(collection_key: str, *, days: int | None = None) -> dict:
    result = {"ok": True, "state": "mirror_needs_attention",
              collection_key: [], "message": _SYNC_MESSAGE}
    if days is not None:
        result["days"] = days
    return result


def _classroom_names(records: list) -> tuple[list[str], dict[str, str] | None]:
    """Build the one privacy projection shared by every roster Panel."""
    full_names = []
    for record in records:
        if not isinstance(record, dict) or not str(record.get("id") or ""):
            return [], None
        full = str(record.get("name") or record.get("display_name") or "").strip()
        if not full:
            return [], None
        if "," in full:
            last, first = (part.strip() for part in full.split(",", 1))
            parts = [part for part in first.split() if part]
            first_name = parts[0] if parts else ""
            last_name = last
        else:
            parts = [part for part in full.split() if part]
            first_name = parts[0] if parts else ""
            last_name = parts[-1] if len(parts) > 1 else ""
        short = f"{first_name} {last_name[0]}." if last_name else first_name
        if not short:
            return [], None
        full_names.append((short.strip(), full, str(record["id"])))

    by_short: dict[str, list[tuple[str, str]]] = {}
    for short, full, uid in full_names:
        by_short.setdefault(short.casefold(), []).append((full, uid))
    projection: dict[str, str] = {}
    for short, full, uid in full_names:
        values = by_short[short.casefold()]
        display = full if len(values) > 1 else short
        if display.casefold() in projection:
            return [], None
        projection[display.casefold()] = uid
    names = sorted(
        (full if len(by_short[short.casefold()]) > 1 else short
         for short, full, _uid in full_names),
        key=str.casefold,
    )
    if len(names) != len(set(name.casefold() for name in names)):
        return [], None
    return names, {
        display: uid for short, full, uid in full_names
        for display in [full if len(by_short[short.casefold()]) > 1 else short]
    }


def _names_payload(course_id: str, *, mirror_root=None, scope_reader=None) -> dict:
    roster = _private_scope(course_id, read_service.PRIVATE_ROSTER,
                            mirror_root=mirror_root, scope_reader=scope_reader)
    if not _current_scope(roster, course_id, read_service.PRIVATE_ROSTER):
        return _attention("names")
    names, mapping = _classroom_names(roster["records"])
    if mapping is None:
        return _attention("names")
    fingerprint = hashlib.sha256(
        json.dumps(names, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {"ok": True, "state": "ready" if names else "no_students",
            "names": names, "fingerprint": fingerprint,
            "message": "" if names else "No students in the current roster."}


def random_student_payload(course_id: str, *, mirror_root=None,
                           scope_reader=None) -> dict:
    return _names_payload(course_id, mirror_root=mirror_root,
                          scope_reader=scope_reader)


def random_student_no_repeats_payload(course_id: str, *, mirror_root=None,
                                      scope_reader=None) -> dict:
    return _names_payload(course_id, mirror_root=mirror_root,
                          scope_reader=scope_reader)


def _safe_assignment_sort(record: dict) -> tuple:
    due = _parse_due(record.get("due_at"))
    return (due.isoformat() if due else "9999-12-31T23:59:59+00:00",
            str(record.get("name") or "Untitled assignment").casefold(),
            str(record.get("id") or ""))


def missing_work_payload(course_id: str, *, mirror_root=None,
                         scope_reader=None) -> dict:
    scopes = {
        read_service.PRIVATE_ROSTER: _private_scope(
            course_id, read_service.PRIVATE_ROSTER,
            mirror_root=mirror_root, scope_reader=scope_reader),
        read_service.PRIVATE_ASSIGNMENTS: _private_scope(
            course_id, read_service.PRIVATE_ASSIGNMENTS,
            mirror_root=mirror_root, scope_reader=scope_reader),
        read_service.PRIVATE_SUBMISSIONS: _private_scope(
            course_id, read_service.PRIVATE_SUBMISSIONS,
            mirror_root=mirror_root, scope_reader=scope_reader),
    }
    if any(not _current_scope(result, course_id, scope) for scope, result in scopes.items()):
        return _attention("students")

    roster_records = scopes[read_service.PRIVATE_ROSTER]["records"]
    names, name_by_id = _classroom_names(roster_records)
    if name_by_id is None:
        return _attention("students")
    roster_ids = {str(record.get("id")) for record in roster_records}
    assignments = {}
    for record in scopes[read_service.PRIVATE_ASSIGNMENTS]["records"]:
        if not isinstance(record, dict) or not str(record.get("id") or ""):
            return _attention("students")
        assignment_id = str(record["id"])
        if assignment_id in assignments:
            return _attention("students")
        assignments[assignment_id] = record

    missing_by_user: dict[str, dict[str, dict]] = {uid: {} for uid in roster_ids}
    for record in scopes[read_service.PRIVATE_SUBMISSIONS]["records"]:
        if not isinstance(record, dict):
            return _attention("students")
        assignment_id = str(record.get("assignment_id") or "")
        user_id = str(record.get("user_id") or "")
        if not assignment_id or not user_id:
            return _attention("students")
        assignment = assignments.get(assignment_id)
        if assignment is None:
            return _attention("students")
        if user_id not in roster_ids:
            continue
        if (assignment.get("published") is True and record.get("missing") is True
                and record.get("excused") is not True):
            missing_by_user[user_id][assignment_id] = assignment

    rows = []
    if not names:
        return {"ok": True, "state": "no_students", "students": [],
                "message": "No students in the current roster."}
    for name, uid in ((display, uid) for display, uid in name_by_id.items()):
        items = sorted(missing_by_user[uid].values(), key=_safe_assignment_sort)
        raw = {"kind": "missing_work", "student_name": name,
               "missing_count": len(items),
               "assignment_titles": [str(item.get("name") or "Untitled assignment")
                                     for item in items]}
        safe = audience.classroom_only([audience.tag(raw)])
        rows.extend(_untagged(item) for item in safe)
    rows.sort(key=lambda row: (-row["missing_count"], row["student_name"].casefold()))
    return {"ok": True, "state": "ready" if any(row["missing_count"] for row in rows)
            else "no_missing_work", "students": rows,
            "message": "" if any(row["missing_count"] for row in rows)
            else "No missing work."}


def _friendly_month_day(value: date) -> str:
    return f"{value.strftime('%b')} {value.day}"


def _birthday_occurrence(month_day: str, year: int) -> date | None:
    try:
        month, day = (int(value) for value in month_day.split("-", 1))
        return date(year, month, day)
    except (AttributeError, TypeError, ValueError):
        return None


def birthdays_celebrations_payload(course_id: str, days=DEFAULT_BIRTHDAY_DAYS,
                                    *, now=None, mirror_root=None,
                                    scope_reader=None, profile_reader=None) -> dict:
    days = clamp_days(days, DEFAULT_BIRTHDAY_DAYS, MAX_BIRTHDAY_DAYS)
    start = _local_date(now)
    end = start + timedelta(days=days)
    roster = _private_scope(course_id, read_service.PRIVATE_ROSTER,
                            mirror_root=mirror_root, scope_reader=scope_reader)
    if not _current_scope(roster, course_id, read_service.PRIVATE_ROSTER):
        return _attention("items", days=days)
    names, name_by_id = _classroom_names(roster["records"])
    if name_by_id is None:
        return _attention("items", days=days)
    if not names:
        return {"ok": True, "state": "no_students", "days": days, "items": [],
                "message": "No students in the current roster."}
    settings = profile_reader(course_id) if profile_reader else config.get_roster_student_settings(course_id)
    if not isinstance(settings, dict):
        return _attention("items", days=days)
    items = []
    for display, uid in name_by_id.items():
        profile = settings.get(uid, {})
        if not isinstance(profile, dict):
            return _attention("items", days=days)
        try:
            profile = config.validate_classroom_profile(
                profile.get("classroom_profile", config.empty_classroom_profile())
            )
        except ValueError:
            return _attention("items", days=days)
        birthday_candidates = []
        if profile["birthday"]:
            birthday_candidates = [candidate for year in (start.year, start.year + 1)
                                   for candidate in [_birthday_occurrence(profile["birthday"], year)]
                                   if candidate and start <= candidate <= end]
        for birthday in birthday_candidates:
            items.append({"kind": "birthday", "student_name": display,
                          "date": _friendly_month_day(birthday), "label": "Birthday"})
        for celebration in profile["celebrations"]:
            c_start = _parse_iso(celebration["start"])
            c_end = _parse_iso(celebration["end"])
            if c_start is None or c_end is None or c_end < start or c_start > end:
                continue
            display_start = max(c_start, start)
            display_end = min(c_end, end)
            span = _friendly_month_day(display_start)
            if display_end != display_start:
                span += "–" + _friendly_month_day(display_end)
            items.append({"kind": "achievement", "student_name": display,
                          "date": span, "label": celebration["label"]})
    safe = audience.classroom_only([audience.tag(item) for item in items])
    items = [_untagged(item) for item in safe]
    items.sort(key=lambda item: (item["date"], item["student_name"].casefold(), item["label"].casefold()))
    return {"ok": True, "state": "ready" if items else "nothing_to_celebrate",
            "days": days, "items": items,
            "message": "" if items else f"Nothing to celebrate in the next {days} days."}
