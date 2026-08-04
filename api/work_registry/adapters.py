"""Read-only projections from local Canvas Expert authorities.

This module deliberately consumes summaries and metadata only. It never opens a
PowerGrader session payload, scans Canvas, or copies private authority fields.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

from .models import material_version, stable_fingerprint, validate_job


_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_-]+$")
_FORGE_FOLDERS = {
    "Quizzes": "quiz",
    "Assignments": "assignment",
    "Pages": "page",
    "Rubrics": "rubric",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _text(value) -> str:
    return value if isinstance(value, str) else ""


def _safe_token(value) -> str:
    value = _text(value)
    return value if value and _SAFE_TOKEN.fullmatch(value) else ""


def _job_id(kind: str, source_value: str) -> str:
    digest = hashlib.sha256(f"{kind}\0{source_value}".encode("utf-8")).hexdigest()
    return f"job-{digest}"


def _project(
    *, kind: str, origin: str, source_type: str, source_value: str,
    course_ids: list[str], assignment_id: str, resume_url: str,
    status: str, counts: dict, attention_reason: str = "",
) -> dict:
    timestamp = _now()
    source_ref = {"type": source_type, "value": source_value}
    fingerprint = stable_fingerprint(kind, source_ref, course_ids, assignment_id)
    facts = {"kind": kind, "course_ids": sorted(course_ids), "assignment_id": assignment_id,
             "status": status, "counts": counts}
    job = {
        "job_id": _job_id(kind, source_value),
        "fingerprint": fingerprint,
        "material_version": material_version(facts),
        "origin": origin,
        "kind": kind,
        "status": status,
        "title": "Work item",
        "description": "",
        "course_ids": list(course_ids),
        "focused_course_id": course_ids[0] if len(course_ids) == 1 else "",
        "assignment_id": assignment_id,
        "resumable_url": resume_url,
        "source_ref": source_ref,
        "counts": dict(counts),
        "attention_reason": attention_reason,
        "created_at": timestamp,
        "updated_at": timestamp,
        "completed_at": timestamp if status == "completed" else "",
    }
    validate_job(job)
    return job


def _powergrader_summary_rank(summary: dict) -> tuple[int, int, str, str]:
    """Rank one summary without opening its private PowerGrader session."""
    total = summary.get("total") if isinstance(summary.get("total"), int) else 0
    approved = summary.get("approved") if isinstance(summary.get("approved"), int) else 0
    posted = summary.get("posted") if isinstance(summary.get("posted"), int) else 0
    unposted = max(approved - posted, 0)
    completed = posted == total and total > 0
    if not completed and unposted:
        priority = 2
    elif not completed:
        priority = 1
    else:
        priority = 0
    return priority, unposted, _text(summary.get("created")), _text(summary.get("session_id"))


def _select_powergrader_summaries(summaries: list[dict]) -> list[dict]:
    """Select one Home resume target per certain course/assignment pair."""
    grouped: dict[tuple[str, str], list[dict]] = {}
    for summary in summaries:
        if not isinstance(summary, dict) or not _safe_token(summary.get("session_id")):
            continue
        course_id = _text(summary.get("course_id"))
        assignment_id = _text(summary.get("assignment_id"))
        if course_id and assignment_id:
            grouped.setdefault((course_id, assignment_id), []).append(summary)

    selected = {
        key: max(group, key=_powergrader_summary_rank)
        for key, group in grouped.items()
    }
    output = []
    emitted: set[tuple[str, str]] = set()
    for summary in summaries:
        if not isinstance(summary, dict) or not _safe_token(summary.get("session_id")):
            continue
        key = (_text(summary.get("course_id")), _text(summary.get("assignment_id")))
        if not all(key):
            output.append(summary)
        elif key not in emitted:
            output.append(selected[key])
            emitted.add(key)
    return output


def _powergrader_jobs() -> list[dict]:
    try:
        from api.powergrader import session_store
        summaries = session_store.list_session_summaries()
    except Exception:
        return []
    output = []
    selected_summaries = _select_powergrader_summaries(summaries) if isinstance(summaries, list) else []
    for summary in selected_summaries:
        if not isinstance(summary, dict):
            continue
        safe_id = _safe_token(summary.get("session_id"))
        if not safe_id:
            continue
        course_id = _text(summary.get("course_id"))
        assignment_id = _text(summary.get("assignment_id"))
        total = summary.get("total") if isinstance(summary.get("total"), int) else 0
        approved = summary.get("approved") if isinstance(summary.get("approved"), int) else 0
        posted = summary.get("posted") if isinstance(summary.get("posted"), int) else 0
        counts = {"total": max(total, 0), "pending": max(total - approved, 0), "affected": max(approved - posted, 0)}
        if posted == total and total > 0:
            status = "completed"
        elif approved > posted:
            status = "attention"
        else:
            status = "in_progress"
        output.append(_project(
            kind="grade.powergrader", origin="intentional", source_type="powergrader_session",
            source_value=safe_id, course_ids=[course_id] if course_id else [],
            assignment_id=assignment_id, resume_url=f"/powergrader/session/{safe_id}",
            status=status, counts=counts,
            attention_reason="PowerGrader review is waiting" if status == "attention" else "",
        ))
    return output


def _autoscore_jobs() -> list[dict]:
    try:
        from api.powergrader import autoscore_queue
        queue = autoscore_queue.load_queue()
    except Exception:
        return []
    output = []
    for entry in (queue.get("jobs", []) if isinstance(queue, dict) else []):
        if not isinstance(entry, dict):
            continue
        queue_id = _safe_token(entry.get("job_id"))
        if not queue_id:
            continue
        state = _text(entry.get("status"))
        if state in {"needs_attention", "failed", "partial_auto_pushed"}:
            status = "attention"
        elif state == "auto_pushed":
            status = "completed"
        else:
            status = "in_progress"
        session_id = _safe_token(entry.get("session_id"))
        output.append(_project(
            kind="grade.powergrader.scheduled", origin="intentional", source_type="autoscore_job",
            source_value=queue_id,
            course_ids=[_text(entry.get("course_id"))] if _text(entry.get("course_id")) else [],
            assignment_id=_text(entry.get("assignment_id")),
            resume_url=f"/powergrader/session/{session_id}" if session_id else "/powergrader",
            status=status, counts={"total": 0, "pending": 0, "affected": 0},
            attention_reason="Scheduled work needs attention" if status == "attention" else "",
        ))
    return output


def _receipt_jobs() -> list[dict]:
    try:
        from api.operation_ledger import receipts
        summaries = receipts.list_receipts()
    except Exception:
        return []
    output = []
    for receipt in summaries if isinstance(summaries, list) else []:
        if not isinstance(receipt, dict):
            continue
        receipt_id = _safe_token(receipt.get("receipt_id"))
        if not receipt_id:
            continue
        state = _text(receipt.get("status"))
        if state in {"applied", "no_effect"}:
            status = "completed"
        elif state in {"partial", "failed", "blocked"}:
            status = "attention"
        else:
            continue
        output.append(_project(
            kind="operation_receipt", origin="system", source_type="operation_receipt",
            source_value=receipt_id, course_ids=[], assignment_id="",
            resume_url=f"/api/receipts/{receipt_id}", status=status,
            counts={"total": 0, "pending": 0, "affected": 0},
            attention_reason="Operation receipt needs attention" if status == "attention" else "",
        ))
    return output


def _routine_jobs() -> list[dict]:
    try:
        from api.webui.routes import routines
        definitions = routines._ROUTINE_DEFS
    except Exception:
        return []
    output = []
    for routine_id in sorted(definitions):
        try:
            state = routines._routine_state(routine_id)
            due = routines._routine_due(state)
        except Exception:
            continue
        if not state.get("enabled") or not due:
            continue
        safe_routine_id = _safe_token(routine_id)
        if not safe_routine_id:
            continue
        output.append(_project(
            kind="routine_state", origin="system", source_type="routine_state",
            source_value=safe_routine_id, course_ids=[], assignment_id="",
            resume_url="/routines", status="attention",
            counts={"total": 0, "pending": 0, "affected": 0},
            attention_reason="Enabled routine is due",
        ))
    return output


def collect_local_jobs() -> list[dict]:
    """Collect only local summary projections; never perform a Canvas read."""
    jobs = []
    for provider in (_powergrader_jobs, _autoscore_jobs, _receipt_jobs, _routine_jobs):
        jobs.extend(provider())
    return jobs


def collect_start_sources() -> list[dict]:
    """List workspace Forge files as relative, generic start metadata only."""
    try:
        from api.webui import workspace
        root_value = workspace.workspace_root()
    except Exception:
        return []
    if not root_value:
        return []
    root = Path(root_value)
    output = []
    for folder, singular in _FORGE_FOLDERS.items():
        directory = root / folder
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            output.append({
                "kind": f"create.{singular}",
                "title": f"{singular.title()} source",
                "path": relative,
            })
    return output
