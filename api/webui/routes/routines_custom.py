"""Custom routine loader for Canvas Expert.

Moved out of routines.py for maintainability.
"""
import glob
import os
import traceback

from .. import config, deps, school_calendar
from ..canvas_client import _canvas_get, _canvas_get_all, _canvas_send
from ..deps import _CUSTOM_DIR
from ..schooldays import _school_days_late, _parse_iso_local
from api import routine_reads
from datetime import datetime, timedelta


def _canvas_read(scope, course_id):
    """Custom-routine ``canvas_read`` tool — delegates to the typed mirror-first
    reader. Returns the full ``{ok, records, error, source, synced_at,
    generation}`` dict so freshness is available without a second read."""
    return routine_reads.read_scope(scope, course_id, live_reader=_canvas_get_all)


def _combined_calendar_for_routines(date_from: str | None = None, date_to: str | None = None) -> dict:
    """Custom-routine ``combined_calendar`` tool.

    Replaces the retired academic-CSV projection with the canonical School
    Calendar: readiness plus no_count_dates, grading_periods, and events for
    the requested range (the whole configured year when unspecified). A
    routine author no longer passes weekend/holiday policy -- Calendar is the
    only source of an exceptional school day.
    """
    bell_schedules, _problems = deps.load_bell_schedules()
    readiness = school_calendar.readiness(bell_schedule_ids=bell_schedules)
    doc, _problems = school_calendar.read()
    if doc is None:
        return {"readiness": readiness, "no_count_dates": [], "grading_periods": [], "events": []}
    start = date_from or doc["coverage"]["start"]
    end = date_to or doc["coverage"]["end"]
    projection, _problems = school_calendar.range_projection(start, end)
    return {
        "readiness": readiness,
        "no_count_dates": sorted(school_calendar.no_count_dates(start, end)),
        "grading_periods": (projection or {}).get("grading_periods", []),
        "events": (projection or {}).get("events", []),
    }


def _routine_sdk(routine_fn):
    """Build the SDK dict passed to custom routine files at load time."""
    return {
        "routine": routine_fn,
        "canvas_get": _canvas_get,
        "canvas_get_all": _canvas_get_all,
        "canvas_send": _canvas_send,
        "canvas_read": _canvas_read,
        "active_courses": config.active_courses,
        "sweep_settings": config.get_sweep_settings,
        "combined_calendar": _combined_calendar_for_routines,
        "school_days_late": _school_days_late,
        "parse_iso_local": _parse_iso_local,
        "datetime": datetime,
        "timedelta": timedelta,
    }


def load_custom_routines(routine_fn, _ROUTINE_DEFS, _ROUTINE_RUNNERS):
    """Load custom routine .py files from the custom routines directory."""
    if not os.path.isdir(_CUSTOM_DIR):
        return
    for path in sorted(glob.glob(os.path.join(_CUSTOM_DIR, "*.py"))):
        if os.path.basename(path).startswith("_"):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                src = fh.read()
            g = _routine_sdk(routine_fn)
            g["__name__"] = "custom_routine_" + os.path.splitext(os.path.basename(path))[0]
            g["__file__"] = path
            exec(compile(src, path, "exec"), g)
        except Exception:
            print(f"[routines] failed to load {os.path.basename(path)}:\n" + traceback.format_exc())