"""Claim and lease helpers for scheduled PowerGrader auto-score jobs."""

from __future__ import annotations

import os
import socket
from datetime import datetime, timedelta, timezone

TERMINAL_STATUSES = {
    "session_ready", "auto_pushed", "partial_auto_pushed",
    "needs_review", "cancelled", "failed",
}


def _text(value) -> str:
    return str(value or "").strip()


def _parse_dt(value: str | None):
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _iso(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.replace(microsecond=0).isoformat()


def _now_iso(now=None) -> str:
    if now is None:
        return _iso(datetime.now().astimezone())
    if isinstance(now, datetime):
        return _iso(now)
    return _iso(_parse_dt(str(now)))


def _now_dt(now=None) -> datetime:
    if now is None:
        current = datetime.now(timezone.utc)
    elif isinstance(now, datetime):
        current = now
    else:
        current = _parse_dt(str(now)) or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current


def _find_job(queue: dict, job_id: str) -> dict | None:
    for job in queue.get("jobs", []):
        if job.get("job_id") == job_id:
            return job
    return None


def machine_id() -> str:
    override = _text(os.environ.get("CANVAS_EXPERT_MACHINE_ID"))
    if override:
        return override
    for value in (os.environ.get("COMPUTERNAME"), os.environ.get("HOSTNAME"), socket.gethostname()):
        text = _text(value)
        if text:
            return text
    return "local-machine"


def _worker_id(worker_id: str | None = None) -> str:
    text = _text(worker_id)
    if text:
        return text
    return machine_id()


def _lease_until(job: dict) -> datetime | None:
    return _parse_dt(job.get("lease_until") or "")


def _claim_owner(job: dict) -> str:
    owner = _text(job.get("claimed_by"))
    if owner:
        return owner
    return _text(job.get("machine_id"))


def lease_expired(job: dict, now=None) -> bool:
    lease_until = _lease_until(job or {})
    if lease_until is None:
        return False
    return lease_until <= _now_dt(now)


def _claim_fields(job: dict, worker: str, now=None, lease_minutes: int = 30) -> None:
    current = _now_dt(now)
    existing_owner = _claim_owner(job)
    is_same_owner = existing_owner == worker
    claimed_at = _text(job.get("claimed_at")) if is_same_owner and _text(job.get("claimed_at")) else _now_iso(current)
    job["claimed_by"] = worker
    job["machine_id"] = worker
    job["claimed_at"] = claimed_at
    job["lease_until"] = _iso(current + timedelta(minutes=int(lease_minutes)))
    job["updated_at"] = _now_iso(current)


def _can_claim(job: dict, worker: str, now=None) -> bool:
    if not job:
        return False
    if job.get("status") in TERMINAL_STATUSES:
        policy = job.get("push_policy") if isinstance(job.get("push_policy"), dict) else {}
        may_push_existing_session = (
            job.get("status") == "session_ready"
            and job.get("auto_push") is True
            and policy.get("enabled") is True
        )
        if not may_push_existing_session:
            return False
    owner = _claim_owner(job)
    if not owner:
        return True
    if owner == worker:
        return True
    lease_until = _lease_until(job)
    if lease_until is None:
        return True
    return lease_until <= _now_dt(now)


def claim_job(
    queue: dict,
    job_id: str,
    *,
    worker_id: str | None = None,
    lease_minutes: int = 30,
    now=None,
) -> tuple[bool, dict | None]:
    job = _find_job(queue or {}, job_id)
    worker = _worker_id(worker_id)
    if not _can_claim(job or {}, worker, now=now):
        return False, None
    if not job:
        return False, None
    _claim_fields(job, worker, now=now, lease_minutes=lease_minutes)
    return True, job


def release_job(
    queue: dict,
    job_id: str,
    *,
    worker_id: str | None = None,
    now=None,
) -> bool:
    job = _find_job(queue or {}, job_id)
    if not job:
        return False
    worker = _worker_id(worker_id)
    if _claim_owner(job) != worker:
        return False
    job["claimed_by"] = ""
    job["machine_id"] = ""
    job["claimed_at"] = ""
    job["lease_until"] = ""
    job["updated_at"] = _now_iso(now)
    return True


def refresh_lease(
    queue: dict,
    job_id: str,
    *,
    worker_id: str | None = None,
    lease_minutes: int = 30,
    now=None,
) -> bool:
    job = _find_job(queue or {}, job_id)
    if not job:
        return False
    if job.get("status") in TERMINAL_STATUSES:
        policy = job.get("push_policy") if isinstance(job.get("push_policy"), dict) else {}
        may_push_existing_session = (
            job.get("status") == "session_ready"
            and job.get("auto_push") is True
            and policy.get("enabled") is True
        )
        if not may_push_existing_session:
            return False
    worker = _worker_id(worker_id)
    owner = _claim_owner(job)
    if owner and owner != worker:
        return False
    if owner == worker or not owner or lease_expired(job, now=now):
        _claim_fields(job, worker, now=now, lease_minutes=lease_minutes)
        return True
    return False