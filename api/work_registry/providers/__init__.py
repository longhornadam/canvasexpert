"""Shared, privacy-minimized helpers for Work Registry discovery providers."""

from __future__ import annotations

import hashlib
import inspect
import re
import time
from copy import deepcopy
from datetime import datetime, timezone

from api.work_registry.models import material_version, stable_fingerprint, validate_job


class DiscoveryDeadline(RuntimeError):
    """The bounded discovery window expired before a request could run."""


class CourseTimeout(RuntimeError):
    """A Canvas request or course exceeded the bounded discovery window."""


class CourseUnavailable(RuntimeError):
    """Canvas could not provide a read-only discovery response."""


class ProviderFailure(RuntimeError):
    """A provider could not reduce its source to an aggregate projection."""


_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_-]+$")


def text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return ""


def safe_id(value) -> str:
    value = text(value)
    return value if value and _SAFE_TOKEN.fullmatch(value) else ""


def as_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str) and value:
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result


def iso_now(value=None) -> str:
    current = as_datetime(value) or datetime.now(timezone.utc)
    return current.astimezone(timezone.utc).isoformat(timespec="seconds")


def check_deadline(deadline: float) -> None:
    if deadline is not None and time.monotonic() >= deadline:
        raise DiscoveryDeadline()


def _callback_accepts_deadline(callback) -> bool:
    try:
        parameters = inspect.signature(callback).parameters.values()
    except (TypeError, ValueError):
        return True
    return any(
        parameter.name == "deadline" or parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters
    )


def call_canvas_get_all(canvas_get_all, path: str, params: dict, deadline: float):
    """Call an injected paginated GET while preserving test-friendly callbacks."""
    check_deadline(deadline)
    kwargs = {"params": params, "timeout": 10}
    if _callback_accepts_deadline(canvas_get_all):
        kwargs["deadline"] = deadline
    try:
        result = canvas_get_all(path, **kwargs)
    except (DiscoveryDeadline, CourseTimeout, CourseUnavailable):
        raise
    except TimeoutError:
        raise CourseTimeout() from None
    except Exception:
        raise CourseUnavailable() from None
    if isinstance(result, tuple) and len(result) == 2:
        data, error = result
        if error:
            message = str(error).casefold()
            if "timeout" in message or "timed out" in message:
                raise CourseTimeout() from None
            raise CourseUnavailable() from None
        result = data
    if result is None:
        raise CourseUnavailable() from None
    if not isinstance(result, list):
        raise ProviderFailure() from None
    check_deadline(deadline)
    return result


def finding(
    *,
    kind: str,
    course_id: str,
    assignment_id: str = "",
    counts: dict[str, int],
    now=None,
    latest_submitted_at: str = "",
    latest_attempt_number: int = 0,
    due_at: str = "",
    title: str = "Work item",
    resumable_url: str = "/",
    source_suffix: str = "",
) -> dict:
    """Build one exact Work Registry job from aggregate facts only."""
    course_id = text(course_id)
    assignment_id = text(assignment_id)
    source_value = ":".join(part for part in (kind, course_id, assignment_id, source_suffix) if part)
    source_ref = {"type": "canvas_finding", "value": source_value}
    normalized_counts = {
        key: max(int(counts.get(key, 0) or 0), 0)
        for key in ("total", "pending", "affected")
    }
    facts = {
        "kind": kind,
        "course_id": course_id,
        "assignment_id": assignment_id,
        "counts": normalized_counts,
        "latest_submitted_at": text(latest_submitted_at),
        "latest_attempt_number": max(int(latest_attempt_number or 0), 0),
        "due_at": text(due_at),
    }
    timestamp = iso_now(now)
    fingerprint = stable_fingerprint(kind, source_ref, [course_id], assignment_id)
    job_id = "finding-" + hashlib.sha256(source_value.encode("utf-8")).hexdigest()
    status = "attention" if normalized_counts["affected"] or normalized_counts["pending"] else "completed"
    job = {
        "job_id": job_id,
        "fingerprint": fingerprint,
        "material_version": material_version(facts),
        "origin": "detected",
        "kind": kind,
        "status": status,
        "title": title,
        "course_ids": [course_id],
        "focused_course_id": course_id,
        "assignment_id": assignment_id,
        "resumable_url": resumable_url,
        "source_ref": source_ref,
        "counts": normalized_counts,
        "attention_reason": "Work needs attention" if status == "attention" else "",
        "created_at": timestamp,
        "updated_at": timestamp,
        "completed_at": timestamp if status == "completed" else "",
    }
    validate_job(job)
    return deepcopy(job)


__all__ = [
    "CourseTimeout", "CourseUnavailable", "DiscoveryDeadline", "ProviderFailure",
    "as_datetime", "call_canvas_get_all", "check_deadline", "finding", "iso_now",
    "safe_id", "text",
]
