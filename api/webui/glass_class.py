"""Local class-mode projections for the Glass classroom display."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from api.mirror import read_service
from api.platform_services import config

from . import clock_time, glass, panel_data


DEFAULT_DUE_DAYS = 7
DEFAULT_CLASSROOM_DAYS = 7
MAX_MISSING_ROWS = 12
MAX_CELEBRATION_ROWS = 12
_PRIVATE_SCOPES = (
    read_service.PRIVATE_ROSTER,
    read_service.PRIVATE_ASSIGNMENTS,
    read_service.PRIVATE_SUBMISSIONS,
)


def get_class_context(
    context: dict,
    *,
    at=None,
    scope_reader=None,
    catalog_reader=None,
    objective_reader=None,
    profile_reader=None,
) -> dict:
    """Return class regions for the course in the resolved block.

    Every region is read and reduced independently.  Readers are keyword seams
    for tests; production readers are disk-only and use the mirror's local
    display intent.
    """
    block = context.get("block") if isinstance(context, dict) else None
    course_id = str(block.get("course_id") or "") if isinstance(block, dict) else ""
    local_at, _simulated = glass.normalize_at(at if at is not None else context.get("at"))
    period = _period_region(context, local_at)
    if not course_id:
        return {
            "state": "no_course",
            "period": period,
            "objective": _region("no_course", "No course is assigned to this class."),
            "due": _region("no_course", "No course is assigned to this class.", assignments=[]),
            "missing": _region("no_course", "No course is assigned to this class.", students=[]),
            "celebrations": _region("no_course", "No course is assigned to this class.", items=[]),
            "random_name": _region("no_course", "No course is assigned to this class.", names=[]),
        }

    scopes = {}

    def read_scope(scope, requested_course_id, **_kwargs):
        if scope not in scopes:
            scopes[scope] = _read_scope(
                scope, requested_course_id, local_at, scope_reader=scope_reader,
            )
        return scopes[scope]

    max_age = config.mirror_serve_max_age_hours()
    catalog_scope = _read_catalog_scope(
        course_id, local_at, max_age=max_age, catalog_reader=catalog_reader,
    )

    objective = _safe_region(
        lambda: panel_data.learning_objective_payload(
            course_id,
            now=local_at,
            catalog_reader=catalog_reader,
            document_reader=objective_reader,
        ),
        "Learning objective unavailable.",
    )
    due = _due_region(course_id, local_at, catalog_scope, catalog_reader)
    missing = _safe_region(
        lambda: panel_data.missing_work_payload(
            course_id, scope_reader=read_scope,
        ),
        "Missing work unavailable.",
    )
    celebrations = _safe_region(
        lambda: panel_data.birthdays_celebrations_payload(
            course_id,
            days=DEFAULT_CLASSROOM_DAYS,
            now=local_at,
            scope_reader=read_scope,
            profile_reader=profile_reader,
        ),
        "Celebrations unavailable.",
    )
    random_name = _safe_region(
        lambda: panel_data.random_student_payload(course_id, scope_reader=read_scope),
        "Roster unavailable.",
    )

    due["as_of"] = _as_of(catalog_scope)
    missing["as_of"] = _as_of(scopes, _PRIVATE_SCOPES)
    celebrations["as_of"] = _as_of(scopes, (read_service.PRIVATE_ROSTER,))
    random_name["as_of"] = _as_of(scopes, (read_service.PRIVATE_ROSTER,))

    if isinstance(missing.get("students"), list):
        missing["students"] = missing["students"][:MAX_MISSING_ROWS]
    if isinstance(celebrations.get("items"), list):
        celebrations["items"] = celebrations["items"][:MAX_CELEBRATION_ROWS]

    states = [objective.get("state"), due.get("state"), missing.get("state"),
              celebrations.get("state"), random_name.get("state")]
    state = "ready" if any(value in {"ready", "no_missing_work", "nothing_to_celebrate",
                                      "nothing_due", "no_students"} for value in states) else "attention"
    return {
        "state": state,
        "course_id": course_id,
        "period": period,
        "objective": _public_objective(objective),
        "due": _public_due(due),
        "missing": _public_missing(missing),
        "celebrations": _public_celebrations(celebrations),
        "random_name": _public_random_name(random_name),
    }


def _read_scope(scope, course_id, local_at, *, scope_reader):
    if scope_reader is not None:
        try:
            result = scope_reader(scope, course_id, intent=read_service.LOCAL_DISPLAY)
        except TypeError:
            result = scope_reader(scope, course_id)
        return result if isinstance(result, dict) else {}
    try:
        return read_service.read(
            scope,
            course_id,
            intent=read_service.LOCAL_DISPLAY,
            max_age_hours=config.mirror_serve_max_age_hours(),
            now=_freshness_now(local_at),
        )
    except Exception:
        return {}


def _read_catalog_scope(course_id, local_at, *, max_age, catalog_reader):
    try:
        return read_service.catalog_assignments(
            course_id,
            catalog_reader=catalog_reader,
            max_age_hours=max_age,
            now=_freshness_now(local_at),
        )
    except Exception:
        return {"state": "unavailable", "source": "none", "records": []}


def _due_region(course_id, local_at, scope, catalog_reader):
    if scope.get("source") == "none":
        return _region("no_catalog", "No local course catalog yet.", assignments=[])
    if scope.get("state") != "current":
        return _region("mirror_needs_attention", "Sync now in Canvas Expert to show what is due.", assignments=[])
    try:
        reader = catalog_reader or panel_data.read_catalog
        catalog_result = reader(course_id)
        catalog = catalog_result.get("catalog") if isinstance(catalog_result, dict) else {}
        now_utc = local_at.astimezone(timezone.utc)
        today = local_at.date()
        horizon = today + timedelta(days=DEFAULT_DUE_DAYS)
        assignments = []
        for record in scope.get("records") or []:
            if not isinstance(record, dict) or record.get("published", True) is False:
                continue
            due = panel_data._parse_due(record.get("due_at"))
            if due is None:
                continue
            due_local = due.astimezone(local_at.tzinfo)
            if not today <= due_local.date() <= horizon:
                continue
            assignments.append({
                "title": str(record.get("name") or "Untitled assignment"),
                "due_at": due.isoformat(),
                "due_date": due_local.date().isoformat(),
                "points": record.get("points_possible"),
                "earlier_today": due.astimezone(timezone.utc) < now_utc,
            })
        assignments.sort(key=lambda item: (item["earlier_today"], item["due_at"], item["title"].casefold()))
        for item in assignments:
            item.pop("earlier_today", None)
        return {
            "ok": True,
            "state": "ready" if assignments else "nothing_due",
            "assignments": assignments,
            "course_name": str(catalog.get("course_name") or "") if isinstance(catalog, dict) else "",
            "message": "" if assignments else f"Nothing due in the next {DEFAULT_DUE_DAYS} days.",
        }
    except Exception:
        return _region("catalog_needs_attention", "What’s due is unavailable.", assignments=[])


def _period_region(context, local_at):
    block = context.get("block") if isinstance(context, dict) else None
    if not isinstance(block, dict):
        return {"state": context.get("state"), "label": "", "remaining_seconds": None, "next": None}
    state = context.get("state")
    clock_value = block.get("ends_at") if state == "in_class" else block.get("starts_at")
    boundary = _today_at(local_at, clock_value)
    remaining = max(0, int((boundary - local_at).total_seconds())) if boundary else None
    return {
        "state": state,
        "name": block.get("name") or block.get("label") or "Class",
        "label": block.get("label") or "",
        "period_ids": block.get("period_ids") or [],
        "boundary_at": boundary.isoformat() if boundary else "",
        "remaining_seconds": remaining,
        "next": context.get("next"),
    }


def _today_at(local_at, value):
    minute = clock_time.parse_time(value)
    if minute is None:
        return None
    return datetime.combine(
        local_at.date(),
        datetime.min.time().replace(hour=minute // 60, minute=minute % 60),
        tzinfo=local_at.tzinfo,
    )


def _freshness_now(local_at):
    return local_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_region(factory, fallback):
    try:
        result = factory()
        return result if isinstance(result, dict) else _region("unavailable", fallback)
    except Exception:
        return _region("unavailable", fallback)


def _region(state, message, **collections):
    return {"ok": True, "state": state, "message": message, **collections}


def _as_of(value, required_scopes=None):
    if required_scopes is None:
        values = [value.get("last_success_at", "")] if isinstance(value, dict) else []
    else:
        values = [value.get(scope, {}).get("last_success_at", "")
                  for scope in required_scopes if isinstance(value.get(scope), dict)]
    values = [str(value) for value in values if value]
    return min(values) if values else ""


def _public_objective(value):
    return {"state": value.get("state", "unavailable"), "objective": value.get("objective", ""),
            "message": value.get("message", "")}


def _public_due(value):
    return {"state": value.get("state", "unavailable"), "assignments": value.get("assignments", []),
            "message": value.get("message", ""), "as_of": value.get("as_of", "")}


def _public_missing(value):
    return {"state": value.get("state", "unavailable"), "students": value.get("students", []),
            "message": value.get("message", ""), "as_of": value.get("as_of", "")}


def _public_celebrations(value):
    return {"state": value.get("state", "unavailable"), "items": value.get("items", []),
            "message": value.get("message", ""), "as_of": value.get("as_of", "")}


def _public_random_name(value):
    return {"state": value.get("state", "unavailable"), "names": value.get("names", []),
            "message": value.get("message", ""), "as_of": value.get("as_of", "")}
