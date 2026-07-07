"""Routines configuration — machine-local automation state (NOT synced).

Uses lazy module-reference so monkeypatches to config._io propagate correctly.
"""
from . import _io as _io_mod


def get_routine_states() -> dict:
    return _io_mod._machine_load().get("routines", {})


def set_routine_state(routine_id: str, patch: dict):
    state = _io_mod._machine_load()
    routines = state.setdefault("routines", {})
    cur = routines.setdefault(routine_id, {})
    cur.update(patch)
    _io_mod._machine_save(state)