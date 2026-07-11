"""Local Work Registry projections and guarded state transitions."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.work_registry import adapters, storage, suppressions
from api.work_registry.models import public_job, validate_registry_document
from api.webui.local_request_guard import require_local_mutation


router = APIRouter(prefix="/api", tags=["work"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _all_jobs() -> list[dict]:
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
    return [public_job(job) for job in projected.values()]


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
    return next((job for job in _all_jobs() if job["job_id"] == job_id), None)


def _conflict(message: str = "job is unknown or stale"):
    return JSONResponse({"ok": False, "error": message}, status_code=409)


def _write_result(result: dict):
    if result.get("ok"):
        return None
    return JSONResponse(result, status_code=503)


@router.get("/work")
def get_work(section: str = "continue"):
    jobs = _section_jobs(section)
    if jobs is None:
        return JSONResponse({"ok": False, "error": "unknown section"}, status_code=400)
    return JSONResponse({"ok": True, "jobs": jobs, "start_sources": adapters.collect_start_sources()})


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
