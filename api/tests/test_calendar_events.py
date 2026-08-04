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
    canonical_dates, canonical_periods, canonical_events, _notes = _parse_calendar_csv(CANONICAL)
    simple_dates, simple_periods, simple_events, _simple_notes = _parse_calendar_csv(SIMPLE)

    expected_dates = ["2027-10-10", "2027-10-11", "2027-10-12"]
    assert canonical_dates == simple_dates == expected_dates
    assert canonical_periods == [
        {"name": "Quarter 1", "code": "Q1", "start": "2027-08-16", "end": "2027-10-15"},
        {"name": "Quarter 2", "code": "Q2", "start": "2027-10-16", "end": "2027-12-20"},
    ]
    assert simple_periods == [
        {"name": "Quarter 1", "code": "QUARTER_1", "start": "2027-08-16", "end": "2027-10-15"},
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
        {"kind": "grading_period_end", "label": "Quarter 1", "code": "QUARTER_1", "end": "2027-10-15"},
    ]


def test_simple_format_derives_unique_codes_in_source_order_when_missing():
    csv_text = (
        "Category,Name,Start Date,End Date\n"
        "Academic Period,Term 1,08/16/2027,10/15/2027\n"
        "Academic Period,Term 1,10/16/2027,12/20/2027\n"
        "Academic Period,!!!,01/05/2028,03/01/2028\n"
    )
    _dates, periods, _events, _notes = _parse_calendar_csv(csv_text)
    assert [p["code"] for p in periods] == ["TERM_1", "TERM_1_2", "PERIOD"]


def test_canonical_header_case_and_padding_still_reads_every_field():
    """Detection folded the header; reading must fold the same way. Title-cased
    underscore headers used to be detected as canonical and then read as empty,
    dropping every row while the import reported success."""
    csv_text = (
        " School_Year , Row_Type ,Code,Name, Start_Date ,End_Date,Report_Issue_Date,Basis\n"
        "2026-27,Holiday,,Labor Day,2026-09-07,2026-09-07,,\n"
        "2026-27,Academic Period,T1,Term 1,2026-08-19,2026-10-09,2026-10-14,\n"
    )
    dates, periods, events, notes = _parse_calendar_csv(csv_text)
    assert dates == ["2026-09-07"]
    assert periods == [
        {"name": "Term 1", "code": "T1", "start": "2026-08-19", "end": "2026-10-09"},
    ]
    assert [e["kind"] for e in events] == [
        "no_school", "grading_period_end", "report_card"]
    assert notes == []


def test_simple_header_case_and_padding_still_reads_every_field():
    csv_text = (
        "category,name, Start Date ,END DATE\n"
        "Student Day Off,Fall Break,10/10/2027,10/12/2027\n"
    )
    dates, _periods, _events, notes = _parse_calendar_csv(csv_text)
    assert dates == ["2027-10-10", "2027-10-11", "2027-10-12"]
    assert notes == []


def test_simple_format_reads_a_plain_holiday_category():
    """"Holiday" is the likeliest word in a teacher's own spreadsheet and used
    to match neither Simple substring, so the row vanished."""
    csv_text = (
        "Category,Name,Start Date,End Date\n"
        "Holiday,Labor Day,2026-09-07,2026-09-07\n"
        "Student Day Off,Staff Development,2026-10-12,2026-10-12\n"
        "No School,Weather Day,2026-11-03,2026-11-03\n"
    )
    dates, _periods, events, notes = _parse_calendar_csv(csv_text)
    assert dates == ["2026-09-07", "2026-10-12", "2026-11-03"]
    assert [e["source_subtype"] for e in events] == [
        "holiday", "student day off", "no school"]
    assert notes == []


def test_canonical_academic_period_derives_a_code_when_the_cell_is_empty():
    """An empty canonical code used to pass the parser as "" and then fail a
    step later in preview_replacement with "code must be a non-empty string"."""
    csv_text = (
        "school_year,row_type,code,name,start_date,end_date,report_issue_date,basis\n"
        "2026-27,Academic Period,,Term 1,2026-08-19,2026-10-09,,\n"
    )
    _dates, periods, events, notes = _parse_calendar_csv(csv_text)
    assert periods == [
        {"name": "Term 1", "code": "TERM_1", "start": "2026-08-19", "end": "2026-10-09"},
    ]
    assert events == [
        {"kind": "grading_period_end", "label": "Term 1", "code": "TERM_1",
         "end": "2026-10-09"},
    ]
    assert notes == []


def test_canonical_supplied_codes_stay_verbatim_and_block_derived_collisions():
    csv_text = (
        "school_year,row_type,code,name,start_date,end_date,report_issue_date,basis\n"
        "2026-27,Academic Period,Quarter_1,Fall Term,08/16/2026,10/15/2026,,\n"
        "2026-27,Academic Period,,Quarter 1,10/16/2026,12/18/2026,,\n"
        "2026-27,Academic Period,,Quarter 1,01/05/2027,03/12/2027,,\n"
    )
    _dates, periods, _events, notes = _parse_calendar_csv(csv_text)
    # Row 2's code travels verbatim, mixed case and all; rows 3 and 4 would both
    # derive QUARTER_1, so they step aside from it and from each other.
    assert [p["code"] for p in periods] == ["Quarter_1", "QUARTER_1_2", "QUARTER_1_3"]
    assert notes == []


def test_notes_name_the_row_and_value_for_an_unrecognized_category():
    csv_text = (
        "Category,Name,Start Date,End Date\n"
        "Pep Rally,Homecoming,2026-09-25,2026-09-25\n"
        "Holiday,Labor Day,2026-09-07,2026-09-07\n"
    )
    dates, _periods, _events, notes = _parse_calendar_csv(csv_text)
    assert dates == ["2026-09-07"]
    assert notes == ["row 2: skipped, unrecognized Category 'Pep Rally'"]


def test_notes_name_the_row_and_value_for_an_unreadable_or_missing_date():
    csv_text = (
        "school_year,row_type,code,name,start_date,end_date,report_issue_date,basis\n"
        "2026-27,Holiday,,Labor Day,not-a-date,2026-09-07,,\n"
        "2026-27,Holiday,,Fall Break,2026-10-12,,,\n"
    )
    dates, _periods, _events, notes = _parse_calendar_csv(csv_text)
    assert dates == []
    assert notes == [
        "row 2: skipped, unreadable date 'not-a-date'",
        "row 3: skipped, missing end date",
    ]


def test_notes_are_empty_when_every_row_parses():
    _dates, _periods, _events, notes = _parse_calendar_csv(SIMPLE)
    assert notes == []
