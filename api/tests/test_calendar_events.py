"""Calendar event projection remains local, selected, and public-only."""
from __future__ import annotations

from api.webui.calendar_csv import _parse_calendar_csv
from api.webui.config import calendars
from api.webui.routes import calendar as calendar_routes


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


def test_set_calendar_stores_only_normalized_public_events():
    calendars.set_calendar("selected", "Selected", ["2027-10-10"], events=[
        {"kind": "no_school", "label": "Break", "start": "2027-10-10",
         "end": "2027-10-11", "source_subtype": "holiday", "source_path": "C:/private.csv"},
        {"kind": "report_card", "label": "Bad", "code": "Q1", "report_issue_date": "bad-date"},
        {"kind": "unknown", "path": "C:/private.csv"},
    ])

    assert calendars.get_calendars()["selected"]["events"] == [{
        "kind": "no_school", "label": "Break", "start": "2027-10-10",
        "end": "2027-10-11", "source_subtype": "holiday",
    }]


def test_old_calendar_settings_without_events_remain_empty(monkeypatch):
    monkeypatch.setattr(calendars._io_mod, "_synced_state", lambda: {
        "calendars": {"old": {"label": "Old", "no_count_dates": ["2027-10-10"],
                              "grading_periods": []}}
    })

    assert calendars.get_combined_calendar_for_range() == {
        "no_count_dates": ["2027-10-10"], "grading_periods": [], "events": []
    }


def test_combined_events_filter_intersecting_spans_dedupe_and_sort():
    calendars.set_calendar("first", "First", ["2027-10-10"], events=[
        {"kind": "grading_period_end", "label": "Quarter 1", "code": "Q1", "end": "2027-10-15"},
        {"kind": "no_school", "label": "Fall Break", "start": "2027-10-10",
         "end": "2027-10-12", "source_subtype": "holiday"},
    ])
    calendars.set_calendar("second", "Second", ["2027-10-12"], events=[
        {"kind": "no_school", "label": "Fall Break", "start": "2027-10-10",
         "end": "2027-10-12", "source_subtype": "holiday"},
        {"kind": "report_card", "label": "Quarter 1", "code": "Q1",
         "report_issue_date": "2027-10-20"},
        {"kind": "no_school", "label": "Winter Break", "start": "2027-12-20",
         "end": "2027-12-31", "source_subtype": "holiday"},
    ])

    combined = calendars.get_combined_calendar_for_range("2027-10-11", "2027-10-20")

    assert combined["no_count_dates"] == ["2027-10-12"]
    assert combined["events"] == [
        {"kind": "no_school", "label": "Fall Break", "start": "2027-10-10",
         "end": "2027-10-12", "source_subtype": "holiday"},
        {"kind": "grading_period_end", "label": "Quarter 1", "code": "Q1", "end": "2027-10-15"},
        {"kind": "report_card", "label": "Quarter 1", "code": "Q1",
         "report_issue_date": "2027-10-20"},
    ]


def test_combined_calendar_skips_malformed_stored_events_without_leaking_fields(monkeypatch):
    monkeypatch.setattr(calendars._io_mod, "_synced_state", lambda: {
        "calendars": {"selected": {"no_count_dates": [], "grading_periods": [], "events": [
            None,
            {"kind": "no_school", "label": "Broken", "start": "not-a-date",
             "end": "2027-10-12", "source_subtype": "holiday", "path": "C:/private.csv"},
            {"kind": "grading_period_end", "label": "Quarter 1", "code": "Q1",
             "end": "2027-10-15", "source_path": "C:/private.csv"},
        ]}}
    })

    combined = calendars.get_combined_calendar_for_range()
    assert combined["events"] == [{
        "kind": "grading_period_end", "label": "Quarter 1", "code": "Q1", "end": "2027-10-15"
    }]
    assert "path" not in repr(combined)


def test_loading_one_selected_file_does_not_import_a_neighboring_sample(tmp_path, monkeypatch):
    selected = tmp_path / "Selected.csv"
    selected.write_text(SIMPLE, encoding="utf-8")
    (tmp_path / "Summer_Session_Sample.csv").write_text(
        "Category,Name,Start Date,End Date\nNo School,Fictional Sample,01/01/2028,01/02/2028\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(calendar_routes, "_calendars_dir", lambda: str(tmp_path))

    response = calendar_routes.load_builtin_calendar("Selected.csv")

    assert response.status_code == 200
    combined = calendars.get_combined_calendar_for_range()
    assert combined["no_count_dates"] == ["2027-10-10", "2027-10-11", "2027-10-12"]
    assert all(event["label"] != "Fictional Sample" for event in combined["events"])
