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
    wanted = str(course_id)

    def mutate(state):
        for course in state.get("saved_courses", []):
            if course["id"] == wanted:
                course["active"] = active
                break

    _io_mod._modify_synced(mutate)


def bookmark_course(course_id: str, course_name: str, nickname: str = ""):
    wanted = str(course_id)

    def mutate(state):
        courses = state.setdefault("saved_courses", [])
        for course in courses:
            if course["id"] == wanted:
                course["name"] = course_name
                course["nickname"] = nickname or course_name
                course["active"] = True
                return
        courses.append({
            "id":       wanted,
            "name":     course_name,
            "nickname": nickname or course_name,
            "active":   True,
        })

    _io_mod._modify_synced(mutate)


def remove_course(course_id: str):
    wanted = str(course_id)
    _io_mod._modify_synced(
        lambda state: state.__setitem__(
            "saved_courses",
            [course for course in state.get("saved_courses", []) if course["id"] != wanted],
        ) or state
    )
