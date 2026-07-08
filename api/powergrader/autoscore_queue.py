"""Local persistence helpers for scheduled PowerGrader auto-score jobs.

This module stays offline-testable: it reads and writes JSON under the synced
workspace and only inspects assignment metadata passed in by callers.
"""
from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime, timedelta, timezone

try:
    from webui import workspace
except ModuleNotFoundError:  # pragma: no cover - package context
    from api.webui import workspace

try:
    from powergrader import autoscore_claims
except ModuleNotFoundError:  # pragma: no cover - package context
    from api.powergrader import autoscore_claims

QUEUE_FILENAME = "autoscore_queue.json"
QUEUE_VERSION = 1
TERMINAL_STATUSES = autoscore_claims.TERMINAL_STATUSES
ELIGIBLE_SUBMISSION_TYPES = {"online_text_entry"}
READABLE_UPLOAD_EXTS = {
    "txt", "md", "csv", "tsv", "json", "py", "js", "ts", "html", "htm", "css",
    "xml", "yml", "yaml", "c", "cc", "cpp", "h", "hpp", "java", "rb", "go", "rs",
    "sh", "bat", "ps1", "sql", "r", "ipynb",
}
UNSUPPORTED_TYPES = {
    "none",
    "on_paper",
    "not_graded",
    "external_tool",
    "discussion_topic",
    "media_recording",
    "student_annotation",
}


def queue_dir() -> str | None:
    root = workspace.workspace_root()
    if not root:
        return None
    d = os.path.join(root, "PowerGrader")
    os.makedirs(d, exist_ok=True)
    return d


def queue_path() -> str | None:
    d = queue_dir()
    if not d:
        return None
    return os.path.join(d, QUEUE_FILENAME)


def _default_queue() -> dict:
    return {"version": QUEUE_VERSION, "jobs": []}


def load_queue() -> dict:
    path = queue_path()
    if not path or not os.path.isfile(path):
        return _default_queue()
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return _default_queue()
    if not isinstance(data, dict):
        return _default_queue()
    data.setdefault("version", QUEUE_VERSION)
    jobs = data.get("jobs")
    if not isinstance(jobs, list):
        data["jobs"] = []
    return data


def save_queue(queue: dict) -> None:
    path = queue_path()
    if not path:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = deepcopy(queue) if isinstance(queue, dict) else _default_queue()
    payload.setdefault("version", QUEUE_VERSION)
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        payload["jobs"] = []
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)


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


def _submission_types(assignment: dict) -> list[str]:
    raw = assignment.get("submission_types")
    if not raw and isinstance(assignment.get("submission"), dict):
        raw = assignment["submission"].get("types")
    if not raw:
        return []
    return [str(item).strip().lower() for item in raw if str(item).strip()]


def _upload_extensions(assignment: dict) -> set[str]:
    sub = assignment.get("submission") if isinstance(assignment.get("submission"), dict) else {}
    raw = assignment.get("allowed_extensions") or (sub or {}).get("allowed_extensions") or []
    out = set()
    for item in raw:
        ext = str(item).strip().lstrip(".").lower()
        if ext:
            out.add(ext)
    return out


def _assignment_snapshot(assignment: dict) -> dict:
    assignment = assignment or {}
    snapshot = {
        "name": _text(assignment.get("name")),
        "submission_types": _submission_types(assignment),
        "allowed_extensions": sorted(_upload_extensions(assignment)),
    }
    for key in ("points_possible", "quiz_id", "quiz_type", "description"):
        value = assignment.get(key)
        if value not in (None, ""):
            snapshot[key] = value
    return snapshot


def _is_readable_upload(assignment: dict) -> bool:
    exts = _upload_extensions(assignment)
    if not exts:
        return False
    return bool(exts & READABLE_UPLOAD_EXTS)


def classify_assignment_for_autoscore(assignment: dict) -> tuple[str, str]:
    types = set(_submission_types(assignment))
    if not types:
        return "unsupported", "no submission types are configured"
    if types & UNSUPPORTED_TYPES:
        joined = ", ".join(sorted(types & UNSUPPORTED_TYPES))
        return "unsupported", f"submission type {joined} is not supported for scheduled auto-score"
    if any(t.startswith("quiz") for t in types) or assignment.get("quiz_id") or assignment.get("quiz_type"):
        return "unsupported", "quiz-based assignments are not supported in this stage"

    if "online_text_entry" in types:
        if types <= {"online_text_entry"}:
            return "eligible", "text entry gives PowerGrader readable response text"
        if types <= {"online_text_entry", "online_upload"}:
            return "eligible", "text entry is available alongside file upload"
        return "needs_attention", "text entry is present, but the mixed submission settings should be checked"

    if types == {"online_upload"}:
        if _is_readable_upload(assignment):
            return "eligible", "file upload includes readable or code-friendly extensions"
        return "needs_attention", "file upload may need teacher review before auto-score"

    if types == {"online_url"}:
        return "needs_attention", "URL submissions are queued for manual review"

    if "online_upload" in types:
        if _is_readable_upload(assignment):
            return "needs_attention", "file upload is readable, but mixed submission settings should be checked"
        return "needs_attention", "file upload is present, but the assignment is mixed"

    if "online_url" in types:
        return "needs_attention", "URL submissions are mixed with other submission settings"

    return "unsupported", "this submission type is not supported for scheduled auto-score"


def scheduled_at_from_due(due_at: str, delay_hours: int = 6) -> str | None:
    due = _parse_dt(due_at)
    if due is None:
        return None
    return _iso(due + timedelta(hours=delay_hours))


def make_job_id(course_id: str, assignment_id: str) -> str:
    return f"{_text(course_id)}_{_text(assignment_id)}"


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


machine_id = autoscore_claims.machine_id
lease_expired = autoscore_claims.lease_expired
claim_job = autoscore_claims.claim_job
release_job = autoscore_claims.release_job
refresh_lease = autoscore_claims.refresh_lease


def _find_job(queue: dict, job_id: str) -> dict | None:
    for job in queue.get("jobs", []):
        if job.get("job_id") == job_id:
            return job
    return None


def _build_job(
    *,
    course_id: str,
    course_name: str,
    assignment_id: str,
    assignment_name: str,
    due_at: str,
    delay_hours: int,
    source: str,
    settings: dict | None,
    assignment: dict | None,
    auto_push: bool = False,
    push_policy: dict | None = None,
    created_at: str,
    updated_at: str,
) -> dict:
    eligibility, reason = classify_assignment_for_autoscore(assignment or {})
    scheduled_at = scheduled_at_from_due(due_at, delay_hours)
    status = "scheduled" if eligibility == "eligible" else "needs_attention"
    policy = deepcopy(push_policy) if isinstance(push_policy, dict) else {
        "enabled": bool(auto_push),
        "allow_grade_push": True,
        "allow_comment_push": True,
        "policy_version": 1,
    }
    policy.setdefault("enabled", bool(auto_push))
    policy.setdefault("allow_grade_push", True)
    policy.setdefault("allow_comment_push", True)
    policy.setdefault("policy_version", 1)
    return {
        "job_id": make_job_id(course_id, assignment_id),
        "course_id": _text(course_id),
        "course_name": _text(course_name),
        "assignment_id": _text(assignment_id),
        "assignment_name": _text(assignment_name),
        "source": _text(source) or "push",
        "status": status,
        "eligibility": eligibility,
        "reason": reason,
        "due_at": _text(due_at),
        "delay_hours": int(delay_hours),
        "scheduled_at": scheduled_at or "",
        "assignment": _assignment_snapshot(assignment or {}),
        "settings": deepcopy(settings) if isinstance(settings, dict) else {},
        "auto_push": bool(auto_push),
        "push_policy": policy,
        "created_at": created_at,
        "updated_at": updated_at,
        "session_id": "",
        "last_error": "",
    }


def upsert_job(
    *,
    course_id: str,
    course_name: str,
    assignment_id: str,
    assignment_name: str,
    due_at: str,
    delay_hours: int = 6,
    source: str = "push",
    settings: dict | None = None,
    assignment: dict | None = None,
    auto_push: bool = False,
    push_policy: dict | None = None,
) -> dict:
    queue = load_queue()
    job_id = make_job_id(course_id, assignment_id)
    now_iso = _now_iso()
    existing = _find_job(queue, job_id)
    job = _build_job(
        course_id=course_id,
        course_name=course_name,
        assignment_id=assignment_id,
        assignment_name=assignment_name,
        due_at=due_at,
        delay_hours=delay_hours,
        source=source,
        settings=settings,
        assignment=assignment,
        auto_push=auto_push,
        push_policy=push_policy,
        created_at=(existing or {}).get("created_at") or now_iso,
        updated_at=now_iso,
    )
    if existing:
        preserve_status = existing.get("status") in TERMINAL_STATUSES
        preserved = {
            "session_id": existing.get("session_id", ""),
            "last_error": existing.get("last_error", ""),
        }
        if preserve_status:
            preserved["status"] = existing.get("status", job["status"])
        existing.clear()
        existing.update(job)
        existing.update(preserved)
        save_queue(queue)
        return existing

    queue.setdefault("jobs", []).append(job)
    save_queue(queue)
    return job


def reconcile_due_date(job: dict, latest_assignment: dict, now=None) -> dict:
    out = deepcopy(job or {})
    if out.get("status") in TERMINAL_STATUSES:
        return out

    latest_due = _text((latest_assignment or {}).get("due_at"))
    parsed_due = _parse_dt(latest_due)
    out["assignment"] = _assignment_snapshot(latest_assignment or {})
    if not latest_due or parsed_due is None:
        out["status"] = "needs_attention"
        out["eligibility"] = "needs_attention"
        out["reason"] = "Canvas due date is missing or unreadable"
        out["due_at"] = latest_due
        out["scheduled_at"] = ""
        out["updated_at"] = _now_iso(now)
        return out

    eligibility, reason = classify_assignment_for_autoscore(latest_assignment or {})
    out["eligibility"] = eligibility
    out["reason"] = reason
    out["due_at"] = latest_due
    out["scheduled_at"] = scheduled_at_from_due(latest_due, int(out.get("delay_hours", 6)) or 6) or ""
    if out.get("status") not in TERMINAL_STATUSES:
        out["status"] = "scheduled" if eligibility == "eligible" else "needs_attention"
    out["updated_at"] = _now_iso(now)
    return out


def update_job(queue: dict, job_id: str, *, now=None, **fields) -> dict | None:
    job = _find_job(queue or {}, job_id)
    if not job:
        return None
    job.update({k: v for k, v in fields.items() if v is not None})
    job["updated_at"] = _now_iso(now)
    return job


def set_job_status(
    queue: dict,
    job_id: str,
    *,
    status: str,
    reason: str | None = None,
    last_error: str | None = None,
    session_id: str | None = None,
    now=None,
) -> dict | None:
    job = update_job(
        queue,
        job_id,
        now=now,
        status=status,
        reason=reason if reason is not None else None,
        last_error=last_error if last_error is not None else None,
        session_id=session_id if session_id is not None else None,
    )
    return job


def due_jobs(queue: dict, now=None) -> list[dict]:
    jobs = (queue or {}).get("jobs", [])
    current = now if isinstance(now, datetime) else _parse_dt(str(now)) if now is not None else datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    due = []
    for job in jobs:
        policy = job.get("push_policy") if isinstance(job.get("push_policy"), dict) else {}
        existing_session_push_due = (
            job.get("status") == "session_ready"
            and job.get("auto_push") is True
            and policy.get("enabled") is True
            and bool(_text(job.get("session_id")))
        )
        if not existing_session_push_due and job.get("status") != "scheduled":
            continue
        if job.get("eligibility") != "eligible":
            continue
        scheduled_at = _parse_dt(job.get("scheduled_at") or "")
        if scheduled_at is None:
            continue
        if scheduled_at <= current:
            due.append(job)
    return due
