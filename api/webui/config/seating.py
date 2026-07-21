"""Private, course-scoped storage for Seating's physical state only."""

from . import _io as _io_mod


SEATING_COURSE_STATE_DEFAULT = {"layouts": [], "modes": []}


def get_seating_course_state(course_id: str) -> dict:
    states = _io_mod._synced_state().get("seating_course_states", {})
    return states.get(str(course_id), SEATING_COURSE_STATE_DEFAULT)


def set_seating_course_state(course_id: str, state: dict):
    _io_mod._modify_synced(
        lambda settings: settings.setdefault("seating_course_states", {}).__setitem__(
            str(course_id), state
        )
    )
