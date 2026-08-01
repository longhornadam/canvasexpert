"""Academic-calendar CSV parsing remains local, selected, and public-only.

The projection/storage side this file used to cover (api.webui.config.calendars,
the legacy /api/calendar/load-builtin route) is retired; see
docs/contracts/canonical-school-calendar-contract.md and test_school_calendar.py
for its replacement.
"""
from __future__ import annotations

from api.webui.calendar_csv import _parse_calendar_csv


CANONICAL = """school_year,row_type,code,name,start_date,end_date,report_issue_date,basis
2027-28,Holiday,,Fall Break,10/10/2027,10/12/2027,,
2027-28,Academic Period,Q1,Quarter 1,08/16/2027,10/15/2027,10/20/2027,
2027-28,Academic Period,Q2,Quarter 2,10/16/2027,12/20/2027,not-a-date,
"""

SIMPLE = """Category,Name,Start Date,End Date
Student Day Off,Fall Break,10/10/2027,10/12/2027
Academic Period,Quarter 1,08/16/2027,10/15/2027
"""


def test_both_csv_shapes_keep_legacy_no_count_dates_and_project_events():
    canonical_dates, canonical_periods, canonical_events = _parse_calendar_csv(CANONICAL)
    simple_dates, simple_periods, simple_events = _parse_calendar_csv(SIMPLE)

    expected_dates = ["2027-10-10", "2027-10-11", "2027-10-12"]
    assert canonical_dates == simple_dates == expected_dates
    assert canonical_periods == [
        {"name": "Quarter 1", "code": "Q1", "start": "2027-08-16", "end": "2027-10-15"},
        {"name": "Quarter 2", "code": "Q2", "start": "2027-10-16", "end": "2027-12-20"},
    ]
    assert simple_periods == [
        {"name": "Quarter 1", "code": "", "start": "2027-08-16", "end": "2027-10-15"},
    ]
    assert canonical_events == [
        {"kind": "no_school", "label": "Fall Break", "start": "2027-10-10",
         "end": "2027-10-12", "source_subtype": "holiday"},
        {"kind": "grading_period_end", "label": "Quarter 1", "code": "Q1", "end": "2027-10-15"},
        {"kind": "report_card", "label": "Quarter 1", "code": "Q1",
         "report_issue_date": "2027-10-20"},
        {"kind": "grading_period_end", "label": "Quarter 2", "code": "Q2", "end": "2027-12-20"},
    ]
    assert simple_events == [
        {"kind": "no_school", "label": "Fall Break", "start": "2027-10-10",
         "end": "2027-10-12", "source_subtype": "student day off"},
        {"kind": "grading_period_end", "label": "Quarter 1", "code": "", "end": "2027-10-15"},
    ]
