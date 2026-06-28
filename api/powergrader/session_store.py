"""Session storage helpers for PowerGrader.

Stores/loads session JSON under <workspace>/PowerGrader/.
"""

import json
import os

from webui import workspace


def pg_dir() -> str | None:
    root = workspace.workspace_root()
    if not root:
        return None
    d = os.path.join(root, "PowerGrader")
    os.makedirs(d, exist_ok=True)
    return d


def session_path(session_id: str) -> str | None:
    d = pg_dir()
    if not d:
        return None
    # Guard against path traversal
    safe_id = "".join(c for c in session_id if c.isalnum() or c == "-")
    return os.path.join(d, f"{safe_id}_session.json")


def safe_session_id(session_id: str) -> str:
    return "".join(c for c in session_id if c.isalnum() or c == "-")


def mode_label(mode: str) -> str:
    return {
        "fast": "Grade Myself",
        "packet": "Use My AI Chat",
        "assisted": "Auto-Score With API",
    }.get(mode or "", mode or "Grade Myself")


def load_session(session_id: str) -> dict | None:
    path = session_path(session_id)
    if not path or not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_session(session: dict):
    path = session_path(session["session_id"])
    if not path:
        return
    with open(path, "w", encoding="utf-8") as f:
        json.dump(session, f, indent=2, ensure_ascii=False)


def list_session_summaries() -> list[dict]:
    """Build a summary list of all saved sessions, newest first."""
    d = pg_dir()
    if not d:
        return []
    sessions = []
    for fname in sorted(os.listdir(d)):
        if not fname.endswith("_session.json"):
            continue
        path = os.path.join(d, fname)
        try:
            with open(path, encoding="utf-8") as f:
                s = json.load(f)
        except Exception:
            continue
        students = s.get("students", [])
        sessions.append({
            "session_id":      s.get("session_id"),
            "assignment_name": s.get("assignment_name"),
            "course_id":       s.get("course_id"),
            "assignment_id":   s.get("assignment_id"),
            "created":         s.get("created"),
            "mode":            s.get("mode"),
            "mode_label":      mode_label(s.get("mode", "fast")),
            "total":           len(students),
            "approved":        sum(1 for st in students if st.get("status") == "approved"),
            "posted":          sum(1 for st in students if st.get("posted")),
        })
    sessions.sort(key=lambda x: x.get("created") or "", reverse=True)
    return sessions