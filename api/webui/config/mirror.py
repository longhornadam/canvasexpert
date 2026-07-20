"""CanvasMirror settings — machine-local (sync cadence is a per-machine
concern; the mirror files themselves live in the synced workspace)."""
from __future__ import annotations

from . import _io as _io_mod

MIRROR_ENABLED_DEFAULT = True
MIRROR_SERVE_MAX_AGE_HOURS_DEFAULT = 6.0


def mirror_enabled() -> bool:
    return bool(_io_mod._machine_load().get("mirror_enabled", MIRROR_ENABLED_DEFAULT))


def set_mirror_enabled(value: bool) -> None:
    _io_mod._modify_machine(
        lambda state: state.__setitem__("mirror_enabled", bool(value)) or state)


def mirror_serve_max_age_hours() -> float:
    """How old a mirror collection may be and still serve reads. Older than
    this, readers fall back to live Canvas (and say so)."""
    raw = _io_mod._machine_load().get("mirror_serve_max_age_hours",
                                      MIRROR_SERVE_MAX_AGE_HOURS_DEFAULT)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return MIRROR_SERVE_MAX_AGE_HOURS_DEFAULT
    return value if value > 0 else MIRROR_SERVE_MAX_AGE_HOURS_DEFAULT


def set_mirror_serve_max_age_hours(hours: float) -> None:
    _io_mod._modify_machine(
        lambda state: state.__setitem__("mirror_serve_max_age_hours", float(hours)) or state)
