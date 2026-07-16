"""Student Reports configuration — synced workspace output root + monitored cohort.

Uses lazy module-reference so monkeypatches to config._io propagate correctly.
"""
import os

from .. import workspace
from . import _io as _io_mod

STUDENT_REPORTS_DEFAULT = os.path.join(
    os.path.expanduser("~"), "Desktop", "Canvas Student Reports")


def get_student_reports_root() -> str:
    state = _io_mod._machine_load()
    if state.get("student_reports_root"):
        return state["student_reports_root"]
    root = workspace.workspace_root()
    if root:
        return os.path.join(root, "Student Reports")
    return STUDENT_REPORTS_DEFAULT


def set_student_reports_root(path: str):
    _io_mod._modify_machine(
        lambda state: state.__setitem__("student_reports_root", path) or state
    )


def get_monitored_students() -> dict:
    return _io_mod._synced_state().get("monitored_students", {})


def set_monitored_student(user_id: str, name: str, note: str = ""):
    _io_mod._modify_synced(
        lambda state: state.setdefault("monitored_students", {}).__setitem__(
            str(user_id), {"name": name, "note": note}
        )
    )


def remove_monitored_student(user_id: str):
    def mutate(state):
        state.setdefault("monitored_students", {}).pop(str(user_id), None)

    _io_mod._modify_synced(mutate)
