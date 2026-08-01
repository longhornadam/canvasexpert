from datetime import datetime

from api.mirror import read_service
from api.webui import panel_data
from api.webui.panel_data import (
    bobcat_hour_payload,
    birthdays_celebrations_payload,
    missing_work_payload,
    random_student_payload,
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


def test_catalog_has_the_four_batch_b_kinds_and_the_four_batch_c_kinds():
    assert set(PANEL_CATALOG) == {
        "whats-due", "upcoming-events", "sports-results", "bobcat-hour",
        "random-student", "random-student-no-repeats", "missing-work",
        "birthdays-celebrations",
    }


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


def _private_scope(scope, records, *, state="current"):
    return {"course_id": "course-c", "scope": scope, "state": state,
            "capability": "supported", "source": "mirror", "records": records}


def test_roster_panels_gate_non_current_scopes_and_strip_identifiers():
    calls = []

    def reader(scope, course_id, **kwargs):
        calls.append((scope, kwargs.get("intent")))
        return _private_scope(scope, [{"id": "student-1", "name": "Alpha One",
                                      "sis_user_id": "private"}], state="stale")

    out = random_student_payload("course-c", scope_reader=reader)

    assert out == {"ok": True, "state": "mirror_needs_attention", "names": [],
                   "message": "Sync now in Canvas Expert to show this panel."}
    assert calls == [(read_service.PRIVATE_ROSTER, read_service.LOCAL_DISPLAY)]
    assert "student-1" not in str(out)


def test_random_names_expand_only_collisions_and_fingerprint_the_safe_set():
    def reader(scope, course_id, **kwargs):
        return _private_scope(scope, [
            {"id": "student-1", "name": "Alpha One", "sis_user_id": "hidden"},
            {"id": "student-2", "name": "Alpha Oak", "sis_user_id": "hidden"},
            {"id": "student-3", "name": "Beta Two"},
        ])

    out = random_student_payload("course-c", scope_reader=reader)

    assert out["names"] == ["Alpha Oak", "Alpha One", "Beta T."]
    assert len(out["fingerprint"]) == 64
    assert "student-" not in str(out)
    assert "sis_user_id" not in str(out)


def test_missing_work_uses_published_missing_and_excused_flags_and_orders_rows():
    scopes = {
        read_service.PRIVATE_ROSTER: _private_scope(read_service.PRIVATE_ROSTER, [
            {"id": "student-1", "name": "Alpha One"},
            {"id": "student-2", "name": "Beta Two"},
        ]),
        read_service.PRIVATE_ASSIGNMENTS: _private_scope(read_service.PRIVATE_ASSIGNMENTS, [
            {"id": "assignment-late", "name": "Later", "due_at": "2026-08-25T12:00:00Z", "published": True},
            {"id": "assignment-soon", "name": "Sooner", "due_at": "2026-08-18T12:00:00Z", "published": True},
            {"id": "assignment-draft", "name": "Draft", "due_at": "2026-08-17T12:00:00Z", "published": False},
        ]),
        read_service.PRIVATE_SUBMISSIONS: _private_scope(read_service.PRIVATE_SUBMISSIONS, [
            {"assignment_id": "assignment-late", "user_id": "student-1", "missing": True, "excused": False},
            {"assignment_id": "assignment-soon", "user_id": "student-1", "missing": True, "excused": True},
            {"assignment_id": "assignment-draft", "user_id": "student-2", "missing": True, "excused": False},
        ]),
    }

    out = missing_work_payload("course-c", scope_reader=lambda scope, course_id, **kwargs: scopes[scope])

    assert out["state"] == "ready"
    assert out["students"] == [
        {"kind": "missing_work", "student_name": "Alpha O.", "missing_count": 1,
         "assignment_titles": ["Later"]},
        {"kind": "missing_work", "student_name": "Beta T.", "missing_count": 0,
         "assignment_titles": []},
    ]
    assert all("student-" not in str(row) for row in out["students"])


def test_birthdays_are_annual_and_celebrations_are_window_intersections():
    scopes = {read_service.PRIVATE_ROSTER: _private_scope(read_service.PRIVATE_ROSTER, [
        {"id": "student-1", "name": "Alpha One"},
        {"id": "student-2", "name": "Beta Two"},
    ])}
    profiles = {
        "student-1": {"classroom_profile": {"birthday": "01-02", "celebrations": []}},
        "student-2": {"classroom_profile": {"birthday": "", "celebrations": [
            {"id": "celebration-1", "label": "Helpful teammate", "start": "2026-12-30", "end": "2027-01-03"}
        ]}},
    }

    out = birthdays_celebrations_payload(
        "course-c", days=7, now=datetime(2026, 12, 29),
        scope_reader=lambda scope, course_id, **kwargs: scopes[scope],
        profile_reader=lambda course_id: profiles,
    )

    assert out["state"] == "ready"
    assert out["items"] == [
        {"kind": "achievement", "student_name": "Beta T.", "date": "Dec 30–Jan 3", "label": "Helpful teammate"},
        {"kind": "birthday", "student_name": "Alpha O.", "date": "Jan 2", "label": "Birthday"},
    ]
    assert "celebration-1" not in str(out)
