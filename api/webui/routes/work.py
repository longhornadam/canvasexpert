"""Local Work Registry projections and guarded state transitions."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.work_registry import adapters, discovery, storage, suppressions
from api.work_registry.models import public_job, validate_registry_document
from .. import config
from ..local_request_guard import require_local_mutation


router = APIRouter(prefix="/api", tags=["work"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _raw_jobs() -> list[dict]:
    registry_jobs = storage.read_registry().get("jobs", [])
    projected = {job["job_id"]: job for job in registry_jobs if isinstance(job, dict)}
    for job in adapters.collect_local_jobs():
        existing = projected.get(job["job_id"])
        if (
            existing
            and existing.get("origin") == "intentional"
            and existing.get("status") == "completed"
            and existing.get("material_version") == job.get("material_version")
        ):
            continue
        projected[job["job_id"]] = job
    current_ids = {
        str(course.get("id") or "").strip()
        for course in config.active_courses()
        if str(course.get("id") or "").strip()
    }
    visible = []
    for job in projected.values():
        course_ids = {
            str(course_id).strip()
            for course_id in (job.get("course_ids") or [])
            if str(course_id).strip()
        }
        if course_ids and not course_ids.intersection(current_ids):
            continue
        visible.append(job)
    return visible


def _all_jobs() -> list[dict]:
    return [public_job(job) for job in _raw_jobs()]


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _count(value) -> int:
    return value if type(value) is int and value >= 0 else 0


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return singular if count == 1 else (plural or f"{singular}s")


def _current_course_labels() -> dict[str, str]:
    try:
        courses = config.active_courses()
    except Exception:
        return {}
    labels = {}
    for course in courses if isinstance(courses, list) else []:
        if not isinstance(course, dict):
            continue
        course_id = _text(course.get("id"))
        label = _text(course.get("nickname")) or _text(course.get("name"))
        if course_id and label:
            labels[course_id] = label
    return labels


def _session_assignment_names() -> dict[str, str]:
    try:
        from api.powergrader import session_store
        summaries = session_store.list_session_summaries()
    except Exception:
        return {}
    names = {}
    for summary in summaries if isinstance(summaries, list) else []:
        if not isinstance(summary, dict):
            continue
        session_id = _text(summary.get("session_id"))
        assignment_name = _text(summary.get("assignment_name"))
        if session_id and assignment_name:
            names[session_id] = assignment_name
    return names


def _scheduled_display_metadata() -> dict[str, tuple[str, str]]:
    try:
        from api.powergrader import autoscore_queue
        queue = autoscore_queue.load_queue()
    except Exception:
        return {}
    metadata = {}
    entries = queue.get("jobs", []) if isinstance(queue, dict) else []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        job_id = _text(entry.get("job_id"))
        if job_id:
            metadata[job_id] = (
                _text(entry.get("assignment_name")),
                _text(entry.get("status")),
            )
    return metadata


def _course_label(job: dict, labels: dict[str, str]) -> str:
    focused = _text(job.get("focused_course_id"))
    if focused in labels:
        return labels[focused]
    for course_id in job.get("course_ids") or []:
        normalized = _text(course_id)
        if normalized in labels:
            return labels[normalized]
    return ""


def _powergrader_summary(counts: dict) -> str:
    total = _count(counts.get("total"))
    pending = _count(counts.get("pending"))
    affected = _count(counts.get("affected"))
    if total == 0:
        return "No students in session"
    prefix = f"{total} {_plural(total, 'student')}"
    if pending == 0 and affected == 0:
        return f"{prefix} · all reviewed and posted"
    clauses = [prefix]
    if pending:
        clauses.append(f"{pending} awaiting review")
    if affected:
        clauses.append(f"{affected} approved, not posted")
    return " · ".join(clauses)


def _scheduled_summary(status: str) -> str:
    if status == "scheduled":
        return "Waiting to run"
    if status == "session_ready":
        return "Draft ready for review"
    if status in {"needs_attention", "needs_review", "failed", "partial_auto_pushed"}:
        return "Needs attention"
    if status in {"auto_pushed", "completed"}:
        return "Completed"
    return "In progress"


def _aggregate_summary(job: dict) -> tuple[str, str, str]:
    counts = job.get("counts") if isinstance(job.get("counts"), dict) else {}
    pending = _count(counts.get("pending"))
    affected = _count(counts.get("affected"))
    total = _count(counts.get("total"))
    kind = _text(job.get("kind"))
    if kind == "grade.debt":
        count = pending
        return (
            "Grading needed",
            f"{count} {_plural(count, 'submission')} awaiting grading",
            "Open PowerGrader",
        )
    if kind == "late.work":
        count = affected
        return "Late work", f"{count} late {_plural(count, 'submission')}", "Open Gradebook"
    if kind == "roster.warning":
        count = affected
        return (
            "Roster attention",
            f"{count} roster {_plural(count, 'issue')} need review",
            "Open Roster",
        )
    count = total or pending or affected
    title = _text(job.get("title")) or "Work item"
    if job.get("status") == "attention":
        summary = f"{count} {_plural(count, 'record')} need review" if count else "Work needs review"
        return title, summary, "Review"
    summary = f"{count} {_plural(count, 'record')} in progress" if count else "Work in progress"
    return title, summary, "Continue"


def _presentations(jobs: list[dict]) -> dict[str, dict[str, str]]:
    labels = _current_course_labels()
    kinds = {_text(job.get("kind")) for job in jobs if isinstance(job, dict)}
    session_names = _session_assignment_names() if "grade.powergrader" in kinds else {}
    scheduled_metadata = (
        _scheduled_display_metadata() if "grade.powergrader.scheduled" in kinds else {}
    )
    presentations = {}
    for job in jobs:
        if not isinstance(job, dict):
            continue
        job_id = _text(job.get("job_id"))
        if not job_id:
            continue
        kind = _text(job.get("kind"))
        source_ref = job.get("source_ref") if isinstance(job.get("source_ref"), dict) else {}
        source_value = _text(source_ref.get("value"))
        if kind == "grade.powergrader":
            title = session_names.get(source_value) or "PowerGrader session"
            summary = _powergrader_summary(job.get("counts") or {})
            action_label = "Review & post" if _count((job.get("counts") or {}).get("affected")) else "Continue grading"
        elif kind == "grade.powergrader.scheduled":
            assignment_name, status = scheduled_metadata.get(source_value, ("", ""))
            title = assignment_name or "Scheduled PowerGrader"
            summary = _scheduled_summary(status)
            action_label = "Open grading"
        else:
            title, summary, action_label = _aggregate_summary(job)
        presentations[job_id] = {
            "course_label": _course_label(job, labels),
            "title": title,
            "summary": summary,
            "action_label": action_label,
        }
    return presentations


def _section_jobs(section: str) -> list[dict] | None:
    if section not in {"continue", "attention", "all"}:
        return None
    jobs = _all_jobs()
    selected = []
    for job in jobs:
        if suppressions.is_suppressed(job):
            continue
        if section == "continue" and job["status"] not in {"draft", "ready", "in_progress"}:
            continue
        if section == "attention" and job["status"] != "attention":
            continue
        selected.append(job)
    return selected


def _json_body_error():
    return JSONResponse({"ok": False, "error": "invalid request body"}, status_code=400)


async def _exact_body(request: Request, keys: set[str]):
    try:
        body = await request.json()
    except Exception:
        return None
    if not isinstance(body, dict) or set(body) != keys:
        return None
    return body


def _find_current(job_id: str):
    return next((job for job in _raw_jobs() if job["job_id"] == job_id), None)


def _conflict(message: str = "job is unknown or stale"):
    return JSONResponse({"ok": False, "error": message}, status_code=409)


def _write_result(result: dict):
    if result.get("ok"):
        return None
    return JSONResponse(result, status_code=503)


def _merge_discovery(result: dict) -> dict:
    current = storage.read_registry()
    scanned_courses = set((result.get("courses") or {}).keys())
    current_jobs = []
    for job in current.get("jobs", []):
        source_ref = job.get("source_ref") if isinstance(job, dict) else {}
        course_ids = set(job.get("course_ids") or []) if isinstance(job, dict) else set()
        if source_ref.get("type") == "canvas_finding" and course_ids & scanned_courses:
            continue
        current_jobs.append(job)
    for record in (result.get("courses") or {}).values():
        current_jobs.extend(record.get("findings") or [])
    current["jobs"] = current_jobs
    current["updated_at"] = _now()
    validate_registry_document(current)
    return storage.write_registry(current)


@router.get("/work")
def get_work(section: str = "continue"):
    jobs = _section_jobs(section)
    if jobs is None:
        return JSONResponse({"ok": False, "error": "unknown section"}, status_code=400)
    return JSONResponse({
        "ok": True,
        "jobs": jobs,
        "presentations": _presentations(jobs),
        "start_sources": adapters.collect_start_sources(),
    })


@router.post("/work/scan")
def scan_work(request: Request):
    require_local_mutation(request)
    if storage.workspace.workspace_root() is None:
        return JSONResponse({"ok": False, "error": "workspace_not_configured"}, status_code=503)
    result = discovery.scan_active_courses()
    if not result.get("ok"):
        return JSONResponse(result, status_code=503)
    write_result = _merge_discovery(result)
    error = _write_result(write_result)
    if error:
        return error
    return JSONResponse({
        "ok": True,
        "partial": bool(result.get("partial")),
        "courses_scanned": result.get("courses_scanned", 0),
        "findings": result.get("findings", 0),
        "stale_course_ids": result.get("stale_course_ids", []),
        "error_codes": result.get("error_codes", []),
    })


@router.post("/work/{job_id}/ignore")
async def ignore_work(job_id: str, request: Request):
    require_local_mutation(request)
    body = await _exact_body(request, {"material_version"})
    if body is None or not isinstance(body.get("material_version"), str):
        return _json_body_error()
    job = _find_current(job_id)
    if job is None or body["material_version"] != job["material_version"]:
        return _conflict()
    result = suppressions.ignore(job)
    error = _write_result(result)
    if error:
        return error
    projection = deepcopy(job)
    projection["status"] = "ignored"
    projection["attention_reason"] = ""
    return JSONResponse({"ok": True, "job": public_job(projection)})


@router.post("/work/{job_id}/snooze")
async def snooze_work(job_id: str, request: Request):
    require_local_mutation(request)
    body = await _exact_body(request, {"material_version", "until"})
    if body is None or not isinstance(body.get("material_version"), str) or not isinstance(body.get("until"), str):
        return _json_body_error()
    job = _find_current(job_id)
    if job is None or body["material_version"] != job["material_version"]:
        return _conflict()
    try:
        result = suppressions.snooze(job, body["until"])
    except ValueError:
        return _conflict("until must be a future ISO-8601 timestamp")
    error = _write_result(result)
    if error:
        return error
    return JSONResponse({"ok": True, "job": public_job(job)})


@router.post("/work/{job_id}/complete")
async def complete_work(job_id: str, request: Request):
    require_local_mutation(request)
    body = await _exact_body(request, {"material_version"})
    if body is None or not isinstance(body.get("material_version"), str):
        return _json_body_error()
    job = _find_current(job_id)
    if job is None or body["material_version"] != job["material_version"]:
        return _conflict()
    if job["origin"] != "intentional":
        return _conflict("only intentional work can be completed")
    current = storage.read_registry()
    existing_index = next((index for index, item in enumerate(current["jobs"]) if item.get("job_id") == job_id), None)
    if existing_index is None:
        completed_record = deepcopy(job)
        completed_record.update({"status": "completed", "completed_at": _now(), "updated_at": _now()})
        current["jobs"].append(completed_record)
        existing_index = len(current["jobs"]) - 1
    else:
        current["jobs"][existing_index].update({"status": "completed", "completed_at": _now(), "updated_at": _now()})
    current["updated_at"] = _now()
    validate_registry_document(current)
    result = storage.write_registry(current)
    error = _write_result(result)
    if error:
        return error
    completed = deepcopy(current["jobs"][existing_index])
    completed.update({"updated_at": current["updated_at"], "attention_reason": ""})
    return JSONResponse({"ok": True, "job": public_job(completed)})
