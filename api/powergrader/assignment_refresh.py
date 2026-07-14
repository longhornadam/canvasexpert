"""Focused, private assignment-evidence refresh for PowerGrader starts.

This is deliberately a small owner, not a general Canvas cache.  It keeps
transport URLs in memory and persists only canonical relative evidence paths.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

try:
    from powergrader import canvas_fetch
    from webui import workspace
except ModuleNotFoundError:
    from api.powergrader import canvas_fetch
    from api.webui import workspace


REFRESH_BINARY_LIMIT = 10 * 1024 * 1024


class RefreshBudget:
    def __init__(self, limit=REFRESH_BINARY_LIMIT):
        self.limit = limit
        self.used = 0

    def reserve(self, size) -> bool:
        try:
            amount = int(size)
        except (TypeError, ValueError):
            return False
        if amount < 0 or amount > self.limit - self.used:
            return False
        self.used += amount
        return True


def _indicator(record):
    return {key: record.get(key) for key in ("size", "updated_at", "modified_at", "created_at", "uuid", "md5")
            if record.get(key) not in (None, "")}


def _relative(path, root):
    if not path or not root or not workspace.path_within_workspace(path, root):
        return None
    return os.path.relpath(path, root)


def _safe_error(record):
    return {key: record.get(key) for key in ("error_code", "error_message", "download_status", "extraction_status")
            if record.get(key) not in (None, "")}


def _existing_records(manifest, root, course_id, assignment_id, kind):
    reusable = {}
    for entry in (manifest or {}).get("evidence", []):
        if entry.get("kind") != kind or entry.get("course_id") != str(course_id) or entry.get("assignment_id") != str(assignment_id):
            continue
        evidence_id = str(entry.get("evidence_id") or "")
        rel = entry.get("relative_path")
        if not evidence_id or not rel:
            continue
        path = os.path.abspath(os.path.join(root, rel))
        if workspace.path_within_workspace(path, root) and os.path.isfile(path):
            reusable[evidence_id] = {"local_path": path, "actual_size": entry.get("actual_size"),
                                     "declared_size": entry.get("declared_size"), "ai_eligible": entry.get("ai_eligible"),
                                     "local_only": entry.get("local_only"), "extraction_status": entry.get("extraction_status"),
                                     "warnings": entry.get("warnings", []), "content_indicator": entry.get("content_indicator", {})}
    return reusable


def refresh_assignment(course_id: str, assignment_id: str, *, session_id: str):
    """Refresh one assignment and return URL-free submission material plus scope state."""
    root = workspace.workspace_root()
    if not root:
        return None, None, {"error": "No workspace configured — finish setup first."}
    try:
        from webui import config
    except ModuleNotFoundError:
        from api.webui import config
    course_name = config.course_display_name(course_id) or course_id
    # Use the immutable ID as the display component for new managed evidence so
    # the record is resolvable before and after the Canvas title response.
    evidence_assignment_name = str(assignment_id)
    existing = workspace.read_assignment_evidence_manifest(course_name, course_id, evidence_assignment_name, assignment_id, root)
    budget = RefreshBudget()
    # Assignment name is learned from the authoritative assignment response.
    subs, assignment, error = canvas_fetch.fetch_submissions(
        course_id, assignment_id, session_id=session_id, byte_budget=budget, evidence_path="managed",
        reusable_records=_existing_records(existing, root, course_id, assignment_id, "new_quiz"),
    )
    if error:
        return None, None, {"error": error}
    assignment = assignment or {}
    course_name = str(assignment.get("course_name") or course_id)
    assignment_name = str(assignment.get("name") or assignment_id)
    conflicts = workspace.assignment_evidence_conflicts(course_name, course_id, evidence_assignment_name, assignment_id, root)
    if not assignment.get("is_quiz_lti_assignment"):
        reusable = _existing_records(existing, root, course_id, assignment_id, "ordinary")

        def target_path(submission, source, filename, attempt):
            user = submission.get("user") or {}
            evidence_id = source.get("id") or source.get("file_id") or source.get("attachment_id")
            return workspace.managed_evidence_path(course_name, course_id, evidence_assignment_name, assignment_id,
                user.get("sortable_name") or user.get("name") or submission.get("user_id"), submission.get("user_id"),
                attempt, evidence_id, filename), attempt

        canvas_fetch.ingest_ordinary_attachments(subs or [], course_name=course_name, course_id=course_id,
            assignment_name=evidence_assignment_name, assignment_id=assignment_id, byte_budget=budget,
            target_path=target_path, reusable_records=reusable, require_identity=True)

    evidence = []
    incomplete = bool(conflicts)
    for submission in subs or []:
        uid = str(submission.get("user_id") or "")
        attempt = submission.get("new_quiz_attempt") or submission.get("attempt") or submission.get("submission_attempt")
        if not uid or attempt in (None, ""):
            incomplete = True
        for attachment in submission.get("attachments") or []:
            item_id = str(attachment.get("item_id") or "")
            source_id = str(attachment.get("evidence_id") or item_id or attachment.get("id") or "")
            kind = "new_quiz" if submission.get("new_quiz_attempt") is not None else "ordinary"
            if kind == "ordinary":
                # Canvas file IDs are the only acceptable ordinary evidence identity.
                source_id = str(attachment.get("item_id") or "")
            rel = _relative(attachment.get("local_path"), root)
            record = {"kind": kind, "course_id": str(course_id), "assignment_id": str(assignment_id),
                "user_id": uid, "submission_id": str(submission.get("id") or ""), "attempt": attempt,
                "evidence_id": source_id, "content_indicator": attachment.get("content_indicator") or _indicator(attachment), "relative_path": rel,
                "declared_size": attachment.get("declared_size"), "actual_size": attachment.get("actual_size"),
                "ai_eligible": bool(attachment.get("ai_eligible")), "local_only": bool(attachment.get("local_only")),
                "extraction_status": attachment.get("extraction_status"), "warnings": attachment.get("warnings") or [],
                "acquisition": _safe_error(attachment)}
            if not source_id or not rel or attachment.get("download_status") not in {"downloaded", "reused"}:
                incomplete = True
            evidence.append(record)
        if submission.get("new_quiz_files_error"):
            incomplete = True
    status = "incomplete" if incomplete else "current"
    manifest = {"version": 1, "course_id": str(course_id), "assignment_id": str(assignment_id),
        "refreshed_at": datetime.now(timezone.utc).isoformat(), "status": status,
        "assignment_indicators": _indicator(assignment), "assignment_name": assignment_name, "evidence": evidence,
        "binary_budget_bytes": REFRESH_BINARY_LIMIT, "binary_bytes_reserved": budget.used}
    path = None
    if not conflicts:
        path = workspace.write_assignment_evidence_manifest(manifest, course_name=course_name, course_id=course_id,
            assignment_name=evidence_assignment_name, assignment_id=assignment_id, root=root)
    if not path:
        status = "incomplete"
    return subs, assignment, {"manifest_path": _relative(path, root), "status": status, "binary_bytes_reserved": budget.used}
