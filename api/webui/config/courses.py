"""Bookmarked courses configuration (synced to workspace).

Uses lazy module-reference so monkeypatches to config._io propagate correctly.
"""
from . import _io as _io_mod


def saved_courses() -> list[dict]:
    """All bookmarked courses [{id, name, nickname, active}].
    `active` defaults to True for older entries that pre-date the field.
    """
    courses = _io_mod._synced_state().get("saved_courses", [])
    for c in courses:
        c.setdefault("active", True)
    return courses


def active_courses() -> list[dict]:
    """Only the active bookmarked courses — used for dashboard dropdowns."""
    return [c for c in saved_courses() if c.get("active", True)]


def set_course_active(course_id: str, active: bool):
    """Mark a bookmarked course active or inactive."""
    state = _io_mod._synced_state()
    for c in state.get("saved_courses", []):
        if c["id"] == str(course_id):
            c["active"] = active
            break
    _io_mod._save_synced_key("saved_courses", state.get("saved_courses", []))


def bookmark_course(course_id: str, course_name: str, nickname: str = ""):
    state = _io_mod._synced_state()
    course_id = str(course_id)
    courses = state.setdefault("saved_courses", [])
    for c in courses:
        if c["id"] == course_id:
            c["name"] = course_name
            c["nickname"] = nickname or course_name
            _io_mod._save_synced_key("saved_courses", courses)
            return
    courses.append({
        "id":       course_id,
        "name":     course_name,
        "nickname": nickname or course_name,
        "active":   True,
    })
    _io_mod._save_synced_key("saved_courses", courses)


def remove_course(course_id: str):
    state = _io_mod._synced_state()
    state["saved_courses"] = [c for c in state.get("saved_courses", [])
                               if c["id"] != str(course_id)]
    _io_mod._save_synced_key("saved_courses", state.get("saved_courses", []))