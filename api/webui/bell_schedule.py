"""Preview/apply service for the teacher's workspace Bell Schedule CSVs."""
from __future__ import annotations

import csv
import hashlib
import io
import os
import re
from pathlib import Path

from api.storage_support import atomic_write_bytes

from . import day_schedule, deps, school_calendar


OPERATION = "bell_schedule_change"
_SCHEDULE_ID_RE = re.compile(r"^bell_schedule_[a-z0-9]+(?:_[a-z0-9]+)*$")
_CSV_COLUMNS = ("period_id", "start", "end", "label")


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _mutation_digest(base_digest: str, mutation: dict) -> str:
    import json

    encoded = json.dumps(
        {"operation": OPERATION, "base_digest": base_digest, "mutation": mutation},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalize_schedule_id(schedule_id) -> tuple[str | None, list[str]]:
    if not isinstance(schedule_id, str) or not schedule_id.strip():
        return None, ["schedule_id must be a non-empty string"]
    normalized = schedule_id.strip().lower()
    if not _SCHEDULE_ID_RE.fullmatch(normalized):
        return None, ["schedule_id must be a canonical bell_schedule_* identifier"]
    return normalized, []


def _canonical_csv(meetings: list[dict]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(_CSV_COLUMNS)
    for meeting in meetings:
        writer.writerow([
            meeting["period_id"], meeting["start"], meeting["end"],
            meeting.get("segment", ""),
        ])
    return output.getvalue()


def _normalize_content(content) -> tuple[dict | None, list[str]]:
    if not isinstance(content, str):
        return None, ["content must be CSV text"]
    meetings, problems = day_schedule.parse_bell_schedule(content)
    if problems:
        return None, problems
    if not meetings:
        return None, ["bell schedule must contain at least one meeting"]
    period_ids = [str(meeting["period_id"]) for meeting in meetings]
    if len(period_ids) != len(set(period_ids)):
        return None, ["period_id values must be unique"]
    normalized = [{
        "period_id": str(meeting["period_id"]),
        "start": str(meeting["start"]),
        "end": str(meeting["end"]),
        "segment": str(meeting.get("segment") or ""),
    } for meeting in meetings]
    return {"content": _canonical_csv(normalized), "meetings": normalized}, []


def _schedule_files(root=None) -> dict[str, dict]:
    return {
        str(entry["schedule_id"]): entry
        for entry in deps.list_bell_schedule_files(root)
    }


def _target_path(schedule_id: str, files: dict[str, dict], root=None) -> str | None:
    existing = files.get(schedule_id)
    if existing:
        return existing["path"]
    directory = deps._calendars_dir(root)
    if not directory:
        return None
    suffix = schedule_id.removeprefix("bell_schedule_").replace("_", " ").title()
    return os.path.join(directory, f"Bell Schedule - {suffix}.csv")


def _current_target(schedule_id: str, files: dict[str, dict], root=None) -> tuple[dict | None, list[str]]:
    path = _target_path(schedule_id, files, root)
    if not path or not os.path.isfile(path):
        return None, []
    try:
        raw = Path(path).read_bytes()
        content = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return None, [f"could not read Bell Schedule '{schedule_id}': {exc}"]
    normalized, problems = _normalize_content(content)
    if problems:
        return None, [f"{schedule_id}: {problem}" for problem in problems]
    return {
        "schedule_id": schedule_id,
        "exists": True,
        "meetings": normalized["meetings"],
        "content_digest": _digest(raw),
    }, []


def _calendar_schedule_ids(root=None) -> tuple[set[str] | None, list[str]]:
    document, problems = school_calendar.read(root)
    if document is None:
        if problems == ["unconfigured"]:
            return set(), []
        return None, problems
    referenced = {
        str(entry.get("schedule_id"))
        for entry in document.get("days", {}).values()
        if isinstance(entry, dict) and entry.get("kind") == "instructional"
    }
    available = set(_schedule_files(root))
    missing = sorted(referenced - available)
    if missing:
        return None, [
            "School Calendar references Bell Schedule IDs with no file: "
            + ", ".join(missing[:5])
        ]
    return available, []


def preview_bell_schedule(*, schedule_id, content, root=None) -> tuple[dict | None, list[str]]:
    normalized_id, problems = _normalize_schedule_id(schedule_id)
    if problems:
        return None, problems
    normalized, problems = _normalize_content(content)
    if problems:
        return None, problems

    files = _schedule_files(root)
    before, problems = _current_target(normalized_id, files, root)
    if problems:
        return None, problems
    available, problems = _calendar_schedule_ids(root)
    if problems:
        return None, problems
    available = set(available or ()) | {normalized_id}
    if before is None and normalized_id in files:
        return None, [f"Bell Schedule '{normalized_id}' is unavailable"]
    if _target_path(normalized_id, files, root) is None:
        return None, ["no workspace available"]

    mutation = {
        "action": "upsert",
        "schedule_id": normalized_id,
        "content": normalized["content"],
    }
    after = {
        "schedule_id": normalized_id,
        "exists": True,
        "meetings": normalized["meetings"],
        "content_digest": _digest(normalized["content"].encode("utf-8")),
    }
    base_digest = before["content_digest"] if before else ""
    preview = {
        "operation": OPERATION,
        "base_digest": base_digest,
        "mutation": mutation,
        "before": before,
        "after": after,
        "is_noop": bool(before and before["content_digest"] == after["content_digest"]),
        "orphaned_schedule_ids": [],
    }
    preview["preview_digest"] = _mutation_digest(base_digest, mutation)
    return preview, []


def apply_bell_schedule(preview: dict, *, expected_digest: str, root=None) -> tuple[dict | None, list[str]]:
    if not isinstance(preview, dict) or preview.get("operation") != OPERATION:
        return None, ["a valid Bell Schedule preview is required"]
    mutation = preview.get("mutation")
    if not isinstance(mutation, dict) or set(mutation) != {"action", "schedule_id", "content"}:
        return None, ["a valid Bell Schedule preview is required"]
    if mutation.get("action") != "upsert":
        return None, ["Bell Schedule preview mutation is not normalized"]
    normalized_id, problems = _normalize_schedule_id(mutation.get("schedule_id"))
    if problems or normalized_id != mutation.get("schedule_id"):
        return None, problems or ["Bell Schedule preview mutation is not normalized"]
    normalized, problems = _normalize_content(mutation.get("content"))
    if problems or normalized["content"] != mutation.get("content"):
        return None, problems or ["Bell Schedule preview mutation is not normalized"]
    if not isinstance(expected_digest, str):
        return None, ["expected_digest must be a string"]
    if preview.get("base_digest") != expected_digest:
        return None, ["stale or altered preview: base digest mismatch"]
    if preview.get("preview_digest") != _mutation_digest(expected_digest, mutation):
        return None, ["stale or altered preview: digest mismatch"]

    files = _schedule_files(root)
    before, problems = _current_target(normalized_id, files, root)
    if problems:
        return None, problems
    current_digest = before["content_digest"] if before else ""
    if current_digest != expected_digest:
        return None, ["stale Bell Schedule: the file changed since preview"]
    if preview.get("before") != before:
        return None, ["stale or altered preview: before projection mismatch"]
    after = {
        "schedule_id": normalized_id,
        "exists": True,
        "meetings": normalized["meetings"],
        "content_digest": _digest(normalized["content"].encode("utf-8")),
    }
    if preview.get("after") != after:
        return None, ["stale or altered preview: after projection mismatch"]
    _available, problems = _calendar_schedule_ids(root)
    if problems:
        return None, problems

    path = _target_path(normalized_id, files, root)
    if not path:
        return None, ["no workspace available"]
    if before and before["content_digest"] == after["content_digest"]:
        return {"schedule_id": normalized_id, "changed": False, **after}, []
    try:
        atomic_write_bytes(Path(path), normalized["content"].encode("utf-8"))
    except OSError as exc:
        return None, [f"could not write Bell Schedule '{normalized_id}': {exc}"]
    return {"schedule_id": normalized_id, "changed": True, **after}, []
