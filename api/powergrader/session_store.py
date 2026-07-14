"""PowerGrader session storage with new-first legacy compatibility reads."""

import json
import os

try:
    from webui import workspace
except ModuleNotFoundError:  # pragma: no cover - package context
    from api.webui import workspace


def pg_dir() -> str | None:
    d = workspace.powergrader_sessions_dir()
    if not d:
        return None
    os.makedirs(d, exist_ok=True)
    return d


def session_path(session_id: str) -> str | None:
    d = pg_dir()
    if not d:
        return None
    # Guard against path traversal
    safe_id = "".join(c for c in session_id if c.isalnum() or c == "-")
    return os.path.join(d, f"{safe_id}_session.json")


def _legacy_session_paths(session_id: str) -> list[str]:
    safe_id = safe_session_id(session_id)
    return workspace.compatibility_paths(f"{safe_id}_session.json", kind="session")


def _read_json(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as f:
            value = json.load(f)
        return value if isinstance(value, dict) else None
    except Exception:
        return None


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
    if path and os.path.isfile(path):
        return _read_json(path)
    for legacy in _legacy_session_paths(session_id):
        value = _read_json(legacy)
        if value is not None:
            return value
    return None


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
    seen_ids = set()
    candidate_paths = []
    if os.path.isdir(d):
        candidate_paths.extend(os.path.join(d, fname) for fname in sorted(os.listdir(d))
                               if fname.endswith("_session.json"))
    root = workspace.workspace_root()
    if root:
        for legacy_dir in (
            os.path.join(root, "PowerGrader"),
            os.path.join(root, workspace.LEGACY_FEEDBACK_NAME, "PRIVATE", "PowerGrader"),
        ):
            if os.path.isdir(legacy_dir):
                candidate_paths.extend(
                    os.path.join(legacy_dir, fname) for fname in sorted(os.listdir(legacy_dir))
                    if fname.endswith("_session.json")
                )
    for path in candidate_paths:
        s = _read_json(path)
        if not s:
            continue
        sid = str(s.get("session_id") or "")
        if sid in seen_ids:
            continue
        seen_ids.add(sid)
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
