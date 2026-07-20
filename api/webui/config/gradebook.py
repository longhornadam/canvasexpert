"""Gradebook tools configuration — extra-time, sweep, tier tags.

Uses lazy module-reference so monkeypatches to config._io propagate correctly.
"""
from . import _io as _io_mod

SWEEP_DEFAULTS = {
    "skip_weekends":    True,
    "holidays":         [],
    "honor_extra_time": True,
}

TIER_NAMES = ["Support", "Core", "Accelerate", "Extend"]


def get_extra_time(course_id: str) -> list[dict]:
    return _io_mod._synced_state().get("extra_time", {}).get(str(course_id), [])


def set_extra_time(course_id: str, students: list[dict]):
    _io_mod._modify_synced(
        lambda state: state.setdefault("extra_time", {}).__setitem__(str(course_id), students)
    )


def get_tier_tags() -> dict:
    saved = _io_mod._synced_state().get("tier_tags", {})
    return {name: str(saved.get(name, "")).strip() for name in TIER_NAMES}


def set_tier_tags(tags: dict):
    clean = {name: str(tags.get(name, "")).strip() for name in TIER_NAMES}
    _io_mod._modify_synced(lambda state: state.__setitem__("tier_tags", clean) or state)


def get_sweep_settings() -> dict:
    saved = _io_mod._synced_state().get("late_sweep", {})
    return {**SWEEP_DEFAULTS, **saved}


def set_sweep_settings(settings: dict):
    _io_mod._modify_synced(
        lambda state: state.__setitem__(
            "late_sweep",
            {k: settings[k] for k in SWEEP_DEFAULTS if k in settings},
        ) or state
    )
