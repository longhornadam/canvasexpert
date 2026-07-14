"""Saved course configuration (synced to workspace).

Uses lazy module-reference so monkeypatches to config._io propagate correctly.
"""
from . import _io as _io_mod


def saved_courses() -> list[dict]:
    """All Current and Previous courses [{id, name, nickname, active}].

    ``active`` is the persisted compatibility field for Current-course
    membership and defaults to True for older entries that pre-date the field.
    """
    courses = _io_mod._synced_state().get("saved_courses", [])
    for c in courses:
        c.setdefault("active", True)
    return courses


def active_courses() -> list[dict]:
    """Current courses, which define Canvas Expert's operational scope."""
    return [c for c in saved_courses() if c.get("active", True)]


def course_display_name(course_id: str) -> str:
    """Return the saved teacher-facing course label for a Canvas course ID."""
    wanted = str(course_id or "").strip()
    for course in saved_courses():
        if str(course.get("id") or "").strip() != wanted:
            continue
        return str(course.get("nickname") or course.get("name") or wanted).strip() or wanted
    return wanted


def set_course_active(course_id: str, active: bool):
    """Move a saved course between the Current and Previous sets."""
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
            c["active"] = True
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
