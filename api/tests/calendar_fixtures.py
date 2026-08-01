"""Shared test helper: write a minimal valid School Calendar.json directly.

Many tests need one or two specific dates resolving to a known schedule_id
without exercising the full create_school_year() API. This writes the
canonical document straight to disk, matching
docs/contracts/canonical-school-calendar-contract.md's schema.
"""
import json
from datetime import date, timedelta
from pathlib import Path


def write_school_calendar(calendars_dir, day_schedule_map, *, coverage_start=None,
                          coverage_end=None, school_year="2026-27", no_count_dates=()):
    """Write School Calendar.json into ``calendars_dir``.

    day_schedule_map: {"YYYY-MM-DD": schedule_id} -- those dates become
    instructional days naming that schedule. Every other date in the
    requested coverage becomes a generated no_school day, unless listed in
    no_count_dates with no schedule (equivalent, kept for readability at
    call sites). Coverage defaults to the min/max of day_schedule_map.
    """
    dates = sorted(day_schedule_map)
    start = coverage_start or dates[0]
    end = coverage_end or dates[-1]
    days = {}
    cursor = date.fromisoformat(start)
    end_d = date.fromisoformat(end)
    while cursor <= end_d:
        key = cursor.isoformat()
        if key in day_schedule_map:
            days[key] = {"kind": "instructional", "schedule_id": day_schedule_map[key]}
        else:
            days[key] = {"kind": "no_school", "schedule_id": None, "label": "No school"}
        cursor += timedelta(days=1)
    payload = {
        "version": "1.0-json",
        "type": "SCHOOL_CALENDAR",
        "revision": 1,
        "school_year": school_year,
        "coverage": {"start": start, "end": end},
        "days": days,
        "grading_periods": [],
        "events": [],
    }
    Path(calendars_dir).mkdir(parents=True, exist_ok=True)
    (Path(calendars_dir) / "School Calendar.json").write_text(
        json.dumps(payload), encoding="utf-8")
