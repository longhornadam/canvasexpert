"""Activity log for Canvas Expert — appends JSON events to a local file.

Pure I/O module: no HTTP here. server.py owns the routes and calls log_event
after each completed operation. Corrupt or missing log file → start fresh;
never raise so a log failure can never kill a push.

Log file location (first match wins):
  1. workspace_root + "activity_log.json"  (when OneDrive workspace exists)
  2. api/webui/activity_log.json            (local fallback)
"""
import json
import os
from datetime import datetime, timezone
from uuid import uuid4

from . import workspace

_WEBUI_DIR = os.path.dirname(os.path.abspath(__file__))
_MAX_EVENTS = 500


def _log_path() -> str:
    root = workspace.workspace_root()
    if root:
        return os.path.join(root, "activity_log.json")
    return os.path.join(_WEBUI_DIR, "activity_log.json")


def _read() -> list:
    path = _log_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _write(events: list):
    path = _log_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=2)
    except Exception:
        pass  # log failures must never propagate


def log_event(action: str, title: str, courses: list[str], ok: bool,
              url: str | None = None, detail: str | None = None):
    """Append one event to the log; trim to newest _MAX_EVENTS."""
    event = {
        "id":      uuid4().hex,
        "ts":      datetime.now(timezone.utc).astimezone().isoformat(),
        "action":  action,
        "title":   title,
        "courses": list(courses),
        "ok":      bool(ok),
        "url":     url,
        "detail":  detail,
    }
    events = _read()
    events.append(event)
    if len(events) > _MAX_EVENTS:
        events = events[-_MAX_EVENTS:]
    _write(events)


def recent(limit: int = 50, action: str | None = None,
           course: str | None = None) -> list:
    """Return newest-first events, optionally filtered by action and/or course."""
    events = _read()
    events.reverse()
    if action:
        events = [e for e in events if e.get("action") == action]
    if course:
        lo = course.lower()
        events = [e for e in events if any(lo in (c or "").lower()
                                           for c in e.get("courses", []))]
    return events[:limit]
