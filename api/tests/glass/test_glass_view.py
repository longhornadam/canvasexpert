"""The render blob: what the whole day looks like once it is shaped for a screen.

Pure tests against a made-up school. Every time, id, label, and club name below
is invented, and every date is in 2099, so nothing here can be mistaken for a
real bell schedule or a real calendar.

The schedule fixture is the same shape as the shipped sample: a Bobcat Hour day
Monday through Thursday, a Friday with lunch inside 4th period and no Bobcat
Hour at all, and a Pep Rally day reachable by a same-day override.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from api.glass import view
from api.glass.schema import (
    BUDGET_LEARNING_GOAL,
    BUDGET_OFFERING_LABEL,
    BUDGET_OFFERING_LOCATION,
    BUDGET_SUCCESS_CRITERION,
    BUDGET_WORK_DETAIL,
    BUDGET_WORK_NAME,
    DAY_PLAN_FORMAT,
    parse_day_plan,
)
from api.schedule.loader import parse_bell_schedule
from api.schedule.models import SCHEDULE_FORMAT

# 2099-09-16 is a Wednesday and 2099-09-18 is a Friday.
WEDNESDAY = date(2099, 9, 16)
THURSDAY = date(2099, 9, 17)
FRIDAY = date(2099, 9, 18)
MONDAY = date(2099, 9, 21)


def _schedule_data(**overrides):
    data = {
        "format": SCHEDULE_FORMAT,
        "school": "Mockingbird Junior High",
        "timezone": "America/Chicago",
        "day_types": {
            "bobcat_hour": {
                "label": "Bobcat Hour Day",
                "blocks": [
                    {"id": "p1", "kind": "class", "label": "1st Period",
                     "start": "08:30", "end": "09:19"},
                    {"id": "p2", "kind": "class", "label": "2nd Period",
                     "start": "09:25", "end": "10:14"},
                    {"id": "bobcat", "kind": "bobcat_hour", "label": "Bobcat Hour",
                     "start": "11:15", "end": "12:15",
                     "sub_blocks": {"mode": "concurrent", "blocks": []}},
                    {"id": "p6", "kind": "class", "label": "6th Period",
                     "start": "14:11", "end": "15:00"},
                ],
            },
            "friday": {
                "label": "Friday",
                "blocks": [
                    {"id": "p1", "kind": "class", "label": "1st Period",
                     "start": "08:30", "end": "09:24"},
                    {"id": "p4", "kind": "class", "label": "4th Period",
                     "start": "11:30", "end": "13:00",
                     "sub_blocks": {"mode": "sequential", "blocks": [
                         {"id": "p4a", "kind": "lunch", "label": "4th Period / A Lunch",
                          "start": "11:30", "end": "12:15"},
                         {"id": "p4b", "kind": "lunch", "label": "4th Period / B Lunch",
                          "start": "12:15", "end": "13:00"},
                     ]}},
                ],
            },
            "pep_rally": {
                "label": "Pep Rally",
                "blocks": [
                    {"id": "p1", "kind": "class", "label": "1st Period",
                     "start": "08:30", "end": "09:18"},
                    {"id": "rally", "kind": "assembly", "label": "Pep Rally",
                     "start": "14:30", "end": "15:00"},
                ],
            },
        },
        "weekday_default": {
            "0": "bobcat_hour", "1": "bobcat_hour",
            "2": "bobcat_hour", "3": "bobcat_hour", "4": "friday",
        },
    }
    data.update(overrides)
    return data


def _schedule(**overrides):
    return parse_bell_schedule(_schedule_data(**overrides))


def _plan_data(on: date, **overrides):
    data = {
        "format": DAY_PLAN_FORMAT,
        "date": on.isoformat(),
        "school_wide": {
            "events": [{"label": "Picture day", "when": "Thursday"}],
            "bobcat_hour_offerings": [
                {"label": "Robotics Club", "location": "Rm 214"},
            ],
        },
        "teacher": {"bobcat_hour_here": {"label": "Essay retakes", "location": "Rm 108"}},
        "sections": {
            "p1": {
                "learning_goal": "Explain how point of view shapes what a reader knows",
                "success_criteria": ["Name the narrator", "Quote one clue"],
                "work": [{"name": "Point of view sort", "detail": "Finish page 2"}],
                "banner": ["Turn in your reading log", "Library books due Friday"],
            },
        },
    }
    data.update(overrides)
    return data


def _plan(on: date, **overrides):
    return parse_day_plan(_plan_data(on, **overrides))


def _build(at: datetime, **kwargs):
    kwargs.setdefault("schedule", _schedule())
    kwargs.setdefault("plan", _plan(at.date()))
    return view.build_view(at=at, **kwargs)


# ------------------------------------------------------------- the whole day


def test_the_blob_carries_every_block_of_the_day_with_its_plan_slice():
    blob = _build(datetime.combine(WEDNESDAY, datetime.min.time()).replace(hour=8, minute=40))

    assert [block["id"] for block in blob["blocks"]] == ["p1", "p2", "bobcat", "p6"]
    first = blob["blocks"][0]
    assert first["start_text"] == "8:30"
    assert first["end_text"] == "9:19"
    assert first["start_seconds"] == 8 * 3600 + 30 * 60
    assert first["plan"]["work"][0]["name"] == "Point of view sort"
    # A block with no plan entry is normal, not an error.
    assert blob["blocks"][1]["plan"]["learning_goal"] == ""


def test_a_mid_block_moment_reports_its_label_countdown_and_progress():
    blob = _build(datetime(2099, 9, 16, 8, 40))

    current = blob["current"]
    assert current["placement"] == "in_block"
    assert current["label"] == "1st Period"
    assert current["block_id"] == "p1"
    assert current["remaining_minutes"] == 39
    assert current["remaining_text"] == "39 min left"
    assert current["percent"] == 20
    assert current["plan"]["learning_goal"].startswith("Explain how point of view")


def test_a_passing_period_counts_down_to_the_next_bell():
    blob = _build(datetime(2099, 9, 16, 9, 22))

    current = blob["current"]
    assert current["placement"] == "passing"
    assert current["next_block_id"] == "p2"
    assert current["remaining_minutes"] == 3
    assert current["countdown"] == "3:00"
    assert current["remaining_text"] == "3 min to 2nd Period"


def test_lunch_inside_a_period_measures_the_half_the_students_are_in():
    blob = _build(datetime(2099, 9, 18, 12, 30), plan=_plan(FRIDAY))

    current = blob["current"]
    assert current["block_id"] == "p4"
    assert current["sub_block_id"] == "p4b"
    assert current["label"] == "4th Period / B Lunch"
    assert current["remaining_minutes"] == 30


def test_a_weekend_still_produces_a_working_page():
    blob = _build(datetime(2099, 9, 19, 10, 0), plan=None)

    assert blob["is_school_day"] is False
    assert blob["blocks"] == []
    assert blob["current"]["label"] == "No school"
    assert blob["day_type"]["label"] == "No school"


def test_the_same_day_override_wins_without_the_calendar_changing():
    plan = _plan(WEDNESDAY, day_type_override="pep_rally")
    blob = _build(datetime(2099, 9, 16, 14, 40), plan=plan)

    assert blob["day_type"]["id"] == "pep_rally"
    assert blob["current"]["label"] == "Pep Rally"


def test_an_override_the_schedule_does_not_define_becomes_a_note_not_a_crash():
    plan = _plan(WEDNESDAY, day_type_override="field_day")
    blob = _build(datetime(2099, 9, 16, 8, 40), plan=plan)

    assert blob["day_type"]["id"] == "bobcat_hour"
    assert any("field_day" in note for note in blob["notes"])


# --------------------------------------------------- the Bobcat Hour heading


def test_the_heading_reads_today_while_the_block_has_not_ended():
    blob = _build(datetime(2099, 9, 16, 8, 40))

    assert blob["bobcat_hour"]["heading"] == "Today during Bobcat Hour"
    assert blob["bobcat_hour"]["is_today"] is True
    assert blob["bobcat_hour"]["offerings"][0]["label"] == "Robotics Club"
    assert blob["bobcat_hour"]["here"]["label"] == "Essay retakes"


def test_the_heading_reads_tomorrow_once_the_block_has_ended():
    blob = _build(datetime(2099, 9, 16, 13, 30), next_plan=_plan(THURSDAY))

    assert blob["bobcat_hour"]["heading"] == "Tomorrow during Bobcat Hour"
    assert blob["bobcat_hour"]["on"] == THURSDAY.isoformat()


def test_a_friday_resolves_forward_to_monday_and_says_so():
    blob = _build(datetime(2099, 9, 18, 9, 0), plan=_plan(FRIDAY))

    assert blob["bobcat_hour"]["heading"] == "Monday during Bobcat Hour"
    assert blob["bobcat_hour"]["on"] == MONDAY.isoformat()


def test_the_heading_is_derived_for_every_weekday_it_can_land_on():
    """One rule over the date, not a fixed set of strings.

    Walking the whole week is the point: a pair of hardcoded morning and
    afternoon states would pass the first two cases above and show an empty pane
    every Friday.
    """
    schedule = _schedule()
    seen = {}
    for offset in range(7):
        on = date(2099, 9, 14) + timedelta(days=offset)
        blob = view.build_view(
            schedule=schedule, plan=None, at=datetime.combine(on, datetime.min.time()),
        )
        seen[on.isoformat()] = blob["bobcat_hour"]["heading"]

    assert seen["2099-09-14"] == "Today during Bobcat Hour"          # Monday
    assert seen["2099-09-17"] == "Today during Bobcat Hour"          # Thursday
    assert seen["2099-09-18"] == "Monday during Bobcat Hour"         # Friday
    assert seen["2099-09-19"] == "Monday during Bobcat Hour"         # Saturday
    assert seen["2099-09-20"] == "Tomorrow during Bobcat Hour"       # Sunday


def test_no_bobcat_hour_anywhere_ahead_says_so_quietly():
    data = _schedule_data()
    del data["day_types"]["bobcat_hour"]
    data["weekday_default"] = {"4": "friday"}
    blob = view.build_view(
        schedule=parse_bell_schedule(data), plan=None, at=datetime(2099, 9, 18, 9, 0),
    )

    assert blob["bobcat_hour"]["available"] is False
    assert blob["bobcat_hour"]["note"] == view.NO_BOBCAT_HOUR_NOTE
    assert blob["bobcat_hour"]["offerings"] == []


def test_a_future_bobcat_hour_with_no_plan_yet_says_where_offerings_come_from():
    blob = _build(datetime(2099, 9, 18, 9, 0), plan=_plan(FRIDAY), next_plan=None)

    assert blob["bobcat_hour"]["heading"] == "Monday during Bobcat Hour"
    assert blob["bobcat_hour"]["note"] == view.OFFERINGS_PENDING_NOTE
    assert blob["bobcat_hour"]["offerings"] == []


def test_the_pane_the_browser_flips_to_is_rendered_alongside_todays():
    blob = _build(datetime(2099, 9, 16, 8, 40), next_plan=_plan(THURSDAY))

    assert blob["bobcat_hour"]["is_today"] is True
    assert blob["bobcat_hour_after"]["heading"] == "Tomorrow during Bobcat Hour"
    assert blob["bobcat_hour_after"]["end_seconds"] == 12 * 3600 + 15 * 60


def test_the_pane_the_browser_flips_to_never_borrows_todays_offerings():
    """Tomorrow's pane takes tomorrow's plan or says nothing.

    The follow-up lookup is anchored at tomorrow, so the occurrence it returns
    reports itself as being on the first day it searched. Trusting that flag put
    today's clubs under tomorrow's heading for the whole afternoon, which is
    exactly the wrong list on a wall.
    """
    blob = _build(datetime(2099, 9, 16, 8, 40), next_plan=None)
    after = blob["bobcat_hour_after"]

    assert after["heading"] == "Tomorrow during Bobcat Hour"
    assert after["is_today"] is False
    assert after["offerings"] == []
    assert after["here"] == {}
    assert after["note"] == view.OFFERINGS_PENDING_NOTE
    # Today's own pane is unaffected and still lists today's plan.
    assert blob["bobcat_hour"]["offerings"][0]["label"] == "Robotics Club"


def test_the_pane_the_browser_flips_to_uses_tomorrows_own_plan_when_it_exists():
    tomorrow_plan = _plan(THURSDAY, school_wide={
        "events": [],
        "bobcat_hour_offerings": [{"label": "Choir sectionals", "location": "Rm 309"}],
    })
    blob = _build(datetime(2099, 9, 16, 8, 40), next_plan=tomorrow_plan)
    after = blob["bobcat_hour_after"]

    assert [offering["label"] for offering in after["offerings"]] == ["Choir sectionals"]
    assert after["note"] == ""


# --------------------------------------------------------- character budgets


def test_every_budgeted_field_clamps_to_its_budget():
    plan = _plan(
        WEDNESDAY,
        school_wide={
            "events": [{"label": "E" * 400, "when": "W" * 100}],
            "bobcat_hour_offerings": [{"label": "L" * 200, "location": "C" * 200}],
        },
        teacher={"bobcat_hour_here": {"label": "H" * 200, "location": "R" * 200}},
        sections={
            "p1": {
                "learning_goal": "G" * 400,
                "success_criteria": ["S" * 200, "T" * 200],
                "work": [{"name": "N" * 200, "detail": "D" * 200}],
                "banner": ["B" * 200],
            },
        },
    )
    blob = _build(datetime(2099, 9, 16, 8, 40), plan=plan)

    current = blob["current"]["plan"]
    assert len(current["learning_goal"]) == BUDGET_LEARNING_GOAL
    for criterion in current["success_criteria"]:
        assert len(criterion) == BUDGET_SUCCESS_CRITERION
    assert len(current["work"][0]["name"]) == BUDGET_WORK_NAME
    assert len(current["work"][0]["detail"]) == BUDGET_WORK_DETAIL

    offering = blob["bobcat_hour"]["offerings"][0]
    assert len(offering["label"]) == BUDGET_OFFERING_LABEL
    assert len(offering["location"]) == BUDGET_OFFERING_LOCATION
    here = blob["bobcat_hour"]["here"]
    assert len(here["label"]) == BUDGET_OFFERING_LABEL
    assert len(here["location"]) == BUDGET_OFFERING_LOCATION

    # The same fields on a block that is not current are clamped too, because the
    # browser swaps to them without asking the server anything.
    assert len(blob["blocks"][0]["plan"]["learning_goal"]) == BUDGET_LEARNING_GOAL


def test_a_field_inside_its_budget_is_left_exactly_as_written():
    blob = _build(datetime(2099, 9, 16, 8, 40))

    assert blob["current"]["plan"]["learning_goal"] == (
        "Explain how point of view shapes what a reader knows"
    )
    assert blob["current"]["plan"]["success_criteria"] == [
        "Name the narrator", "Quote one clue",
    ]


# ---------------------------------------------------------- missing pieces


def test_no_bell_schedule_still_produces_a_page_with_a_note():
    blob = view.build_view(
        schedule=None, plan=None, at=datetime(2099, 9, 16, 8, 40),
        notes=["No bell schedule yet. Copy the template and fill in your own bells."],
    )

    assert blob["has_schedule"] is False
    assert blob["blocks"] == []
    assert blob["current"]["label"] == "No school"
    assert "No bell schedule yet" in blob["rail_notes"]
    assert blob["notes"]


def test_a_sample_schedule_is_marked_in_the_rail():
    schedule = _schedule(sample=True)
    blob = _build(datetime(2099, 9, 16, 8, 40), schedule=schedule)

    assert blob["is_sample"] is True
    assert "Sample schedule" in blob["rail_notes"]


def test_a_missing_plan_leaves_the_focus_area_empty_and_says_so():
    blob = _build(datetime(2099, 9, 16, 8, 40), plan=None)

    assert blob["has_plan"] is False
    assert blob["current"]["plan"]["learning_goal"] == ""
    assert blob["banner"] == []
    assert blob["events"] == []
    assert "No plan for today" in blob["rail_notes"]
    # The day itself still resolves, which is the whole point.
    assert blob["current"]["label"] == "1st Period"
    assert len(blob["blocks"]) == 4


def test_a_calendar_no_school_date_beats_the_weekly_pattern():
    blob = _build(
        datetime(2099, 9, 16, 8, 40),
        no_school_dates=frozenset({WEDNESDAY}),
    )

    assert blob["is_school_day"] is False
    assert blob["blocks"] == []


def test_the_instant_is_a_parameter_and_the_frozen_flag_travels_with_it():
    blob = _build(datetime(2099, 9, 16, 8, 40), clock_frozen=True)

    assert blob["clock_frozen"] is True
    assert blob["at"] == "2099-09-16T08:40:00"
    assert blob["at_seconds"] == 8 * 3600 + 40 * 60
    assert blob["clock"] == "8:40"
    assert blob["weekday"] == "Wednesday"


@pytest.mark.parametrize("hour,minute,expected", [
    (8, 30, "8:30"),
    (12, 5, "12:05"),
    (13, 10, "1:10"),
    (0, 7, "12:07"),
])
def test_wall_clock_text_reads_the_way_a_room_reads_it(hour, minute, expected):
    blob = _build(datetime(2099, 9, 16, hour, minute))

    assert blob["clock"] == expected
