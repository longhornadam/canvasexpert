"""Local class-display projections used by Glass.

This module is deliberately independent of the retired Panels route.  It keeps
the small classroom projections Glass needs while leaving the broader public
Calendar projections in their owning services.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from api import audience, learning_objectives
from api.course_catalog import read_catalog
from api.mirror import read_service
from api.platform_services import config


DEFAULT_BIRTHDAY_DAYS = 7
MAX_BIRTHDAY_DAYS = 31
_PRIVATE_SCOPE_NAMES = {
    read_service.PRIVATE_ROSTER,
    read_service.PRIVATE_ASSIGNMENTS,
    read_service.PRIVATE_SUBMISSIONS,
}


def clamp_days(value, default: int, maximum: int) -> int:
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


def _parse_iso(value) -> date | None:
    try:
        parsed = date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.isoformat() == str(value) else None


def _untagged(item: dict) -> dict:
    return {key: value for key, value in item.items() if key != "audience"}


def _parse_due(value):
    """A Canvas ``due_at`` as an aware UTC datetime, or None."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def learning_objective_payload(course_id: str, *, now=None, catalog_reader=None,
                               document_reader=None) -> dict:
    """Render one reviewed objective from disk and current local evidence."""
    if not course_id:
        return {"ok": True, "state": "no_course", "objective": "",
                "message": "Choose a course for this class."}
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
    reader = catalog_reader or read_catalog
    try:
        read_result = reader(course_id)
        catalog = read_result.get("catalog") if isinstance(read_result, dict) else None
        if not isinstance(catalog, dict) or catalog.get("version") != 3:
            raise learning_objectives.CatalogNeedsAttentionError("catalog unavailable")
        entry = learning_objectives.normalize_entry(covering[0])
        if learning_objectives.source_digest(catalog, entry["source_refs"]) != entry["source_digest"]:
            raise learning_objectives.ChangedSourceError("source changed")
    except learning_objectives.ChangedSourceError:
        return {"ok": True, "state": "changed_source", "objective": "",
                "message": "Objective needs review."}
    except learning_objectives.CatalogNeedsAttentionError:
        return {"ok": True, "state": "catalog_needs_attention", "objective": "",
                "message": "Catalog needs attention. Refresh it in Canvas Expert."}
    except Exception:
        return {"ok": True, "state": "catalog_needs_attention", "objective": "",
                "message": "Catalog needs attention. Refresh it in Canvas Expert."}
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


def _private_scope(course_id: str, scope: str, *, mirror_root=None,
                   scope_reader=None) -> dict | None:
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
              collection_key: [],
              "message": "Sync now in Canvas Expert to show this class region."}
    if days is not None:
        result["days"] = days
    return result


def _classroom_names(records: list) -> tuple[list[str], dict[str, str] | None]:
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
    return {"ok": True, "state": "ready" if names else "no_students",
            "names": names,
            "message": "" if names else "No students in the current roster."}


def random_student_payload(course_id: str, *, mirror_root=None,
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
        if raw["missing_count"] > 0:
            rows.extend(_untagged(item) for item in safe)
    rows.sort(key=lambda row: (-row["missing_count"], row["student_name"].casefold()))
    ready = any(row["missing_count"] for row in rows)
    return {"ok": True, "state": "ready" if ready else "no_missing_work",
            "students": rows,
            "message": "" if ready else "No missing work."}


def _friendly_month_day(value: date) -> str:
    return f"{value.strftime('%b')} {value.day}"


def _birthday_occurrence(month_day: str, year: int) -> date | None:
    try:
        month, day = (int(value) for value in month_day.split("-", 1))
        if month == 2 and day == 29:
            try:
                return date(year, month, day)
            except ValueError:
                return date(year, 2, 28)
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
                          "date": _friendly_month_day(birthday), "label": "Birthday",
                          "_sort_date": birthday})
        for celebration in profile["celebrations"]:
            c_start = _parse_iso(celebration["start"])
            c_end = _parse_iso(celebration["end"])
            if c_start is None or c_end is None or c_end < start or c_start > end:
                continue
            display_start = max(c_start, start)
            display_end = min(c_end, end)
            span = _friendly_month_day(display_start)
            if display_end != display_start:
                span += " to " + _friendly_month_day(display_end)
            items.append({"kind": "achievement", "student_name": display,
                          "date": span, "label": celebration["label"],
                          "_sort_date": display_start})
    safe = audience.classroom_only([audience.tag(item) for item in items])
    items = [_untagged(item) for item in safe]
    items.sort(key=lambda item: (item["_sort_date"], item["student_name"].casefold(),
                                 item["label"].casefold()))
    for item in items:
        del item["_sort_date"]
    return {"ok": True, "state": "ready" if items else "nothing_to_celebrate",
            "days": days, "items": items,
            "message": "" if items else f"Nothing to celebrate in the next {days} days."}
