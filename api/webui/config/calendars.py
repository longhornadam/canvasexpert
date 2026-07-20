"""Academic calendars — district no-count dates for sweep / extensions.

Uses lazy module-reference so monkeypatches to config._io propagate correctly.
"""
from . import _io as _io_mod


def get_calendars() -> dict:
    return dict(_io_mod._synced_state().get("calendars", {}))


def set_calendar(key: str, label: str, dates: list,
                 periods: list | None = None) -> None:
    def mutate(state):
        state.setdefault("calendars", {})[key] = {
            "label":          label,
            "no_count_dates": sorted(set(dates)),
            "grading_periods": periods or [],
        }

    _io_mod._modify_synced(mutate)


def remove_calendar(key: str) -> None:
    def mutate(state):
        state.setdefault("calendars", {}).pop(key, None)

    _io_mod._modify_synced(mutate)


def clear_all_calendars() -> None:
    _io_mod._modify_synced(
        lambda state: state.__setitem__("calendars", {}) or state
    )


def get_combined_calendar_for_range(
        date_from: str | None = None,
        date_to:   str | None = None) -> dict:
    no_count: set = set()
    periods:  list = []
    for cal in _io_mod._synced_state().get("calendars", {}).values():
        for d in cal.get("no_count_dates", []):
            if date_from and d < date_from: continue
            if date_to   and d > date_to:   continue
            no_count.add(d)
        for gp in cal.get("grading_periods", []):
            if date_from and gp["end"]   < date_from: continue
            if date_to   and gp["start"] > date_to:   continue
            periods.append(gp)
    return {
        "no_count_dates": sorted(no_count),
        "grading_periods": sorted(periods, key=lambda p: p["start"]),
    }
