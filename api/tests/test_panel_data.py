from datetime import datetime

from api.webui.panel_data import (
    bobcat_hour_payload,
    upcoming_events_payload,
    sports_results_payload,
)
from api.webui.routes.panels import PANEL_CATALOG


NOW = datetime(2026, 8, 17, 12, 20)


def _projection(events=None, *, days=None, periods=None):
    return {
        "days": days or {},
        "grading_periods": periods or [],
        "events": events or [],
    }


def _reader(projection):
    return lambda _start, _end: (projection, [])


def test_catalog_has_only_the_four_batch_b_kinds():
    assert set(PANEL_CATALOG) == {"whats-due", "upcoming-events", "sports-results", "bobcat-hour"}


def test_upcoming_unions_public_events_and_academic_facts_and_strips_claimed_audience():
    projection = _projection(
        events=[
            {"id": "game-1", "kind": "game", "label": "Game", "shape": "date",
             "date": "2026-08-18", "audience": "teacher"},
            {"id": "private", "kind": "student_id", "label": "No", "shape": "date",
             "date": "2026-08-18", "audience": "classroom"},
        ],
        days={"2026-08-19": {"kind": "no_regular_classes", "label": "Assembly day"}},
        periods=[{"code": "Q1", "name": "Quarter 1", "start": "2026-08-01",
                  "end": "2026-08-20", "report_issue_date": "2026-08-21"}],
    )
    out = upcoming_events_payload(14, now=NOW, projection_reader=_reader(projection))

    assert out["state"] == "ready"
    assert [item["kind"] for item in out["events"]] == [
        "game", "day_type", "grading_period_end", "report_card",
    ]
    assert all("audience" not in item for item in out["events"])
    assert out["events"][1]["label"] == "Assembly day"


def test_upcoming_and_sports_windows_are_clamped_and_sports_is_newest_first():
    events = [
        {"id": "old", "kind": "game", "label": "Old", "shape": "date",
         "date": "2026-01-01", "result": "Won"},
        {"id": "recent", "kind": "game", "label": "Recent", "shape": "date",
         "date": "2026-08-16", "result": "2–1"},
        {"id": "newest", "kind": "game", "label": "Newest", "shape": "date",
         "date": "2026-08-17", "result": "Placed 1st"},
        {"id": "pending", "kind": "game", "label": "Pending", "shape": "date",
         "date": "2026-08-17", "result": ""},
    ]
    projection = _projection(events=events)

    upcoming = upcoming_events_payload(999, now=NOW, projection_reader=_reader(projection))
    sports = sports_results_payload(999, now=NOW, projection_reader=_reader(projection))

    assert upcoming["days"] == 60
    assert sports["days"] == 90
    assert [item["label"] for item in sports["games"]] == ["Newest", "Recent"]
    assert all(item["result"] for item in sports["games"])


def _calendar(schedule_id="bell_schedule_bobcat_hour", *, kind="instructional"):
    return {
        "days": {"2026-08-17": {"kind": kind,
                                  "schedule_id": schedule_id if kind == "instructional" else None,
                                  "label": "No school" if kind != "instructional" else ""}},
        "coverage": {"start": "2026-08-17", "end": "2026-08-17"},
    }


BOBCAT_SCHEDULE = {"bell_schedule_bobcat_hour": [
    {"period_id": "bobcat_a", "start": "12:11", "end": "12:41"},
    {"period_id": "bobcat_b", "start": "12:43", "end": "13:13"},
]}


def test_bobcat_groups_matching_activities_and_exposes_current_block():
    events = [
        {"id": "club-2", "kind": "club", "label": "Z Club", "detail": "Room 2",
         "shape": "date", "date": "2026-08-17", "from": "12:43", "to": "13:13"},
        {"id": "tutorial-2", "kind": "tutorial", "label": "B Tutorial", "detail": "Room 1",
         "shape": "weekdays", "weekdays": [0], "effective_start": "2026-08-01",
         "effective_end": "2026-08-31", "from": "12:11", "to": "12:41"},
        {"id": "outside", "kind": "club", "label": "Outside", "shape": "date",
         "date": "2026-08-17", "from": "12:30", "to": "12:50"},
    ]
    out = bobcat_hour_payload(
        now=NOW,
        calendar_reader=lambda: (_calendar(), []),
        bell_schedule_reader=lambda: (BOBCAT_SCHEDULE, []),
        projection_reader=_reader(_projection(events=events)),
    )

    assert out["state"] == "ready"
    assert out["current_block"] == "A"
    assert [item["label"] for item in out["groups"]["A"]["tutorial"]] == ["B Tutorial"]
    assert [item["label"] for item in out["groups"]["B"]["club"]] == ["Z Club"]
    assert "Outside" not in [item["label"] for item in out["activities"]]


def test_bobcat_preserves_calendar_states_and_rejects_other_instructional_schedule():
    other = bobcat_hour_payload(
        now=NOW,
        calendar_reader=lambda: (_calendar("regular"), []),
        bell_schedule_reader=lambda: ({"regular": []}, []),
        projection_reader=_reader(_projection()),
    )
    no_school = bobcat_hour_payload(
        now=NOW,
        calendar_reader=lambda: (_calendar(kind="no_school"), []),
        bell_schedule_reader=lambda: (BOBCAT_SCHEDULE, []),
        projection_reader=_reader(_projection()),
    )

    assert other["state"] == "not_bobcat_hour_day"
    assert no_school["state"] == "no_school"
    assert no_school["groups"] == {"A": {"tutorial": [], "club": []},
                                    "B": {"tutorial": [], "club": []}}
