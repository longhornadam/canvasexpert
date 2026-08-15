"""Acceptance examples for the offline Glass schedule resolver."""

from datetime import datetime, timezone

from api.webui import glass


def _meeting(period_id, start, end, segment=""):
    return {"period_id": period_id, "start": start, "end": end, "segment": segment}


def _calendar():
    days = {}
    for date_key, schedule_id in (
        ("2026-09-01", "bobcat"),
        ("2026-09-02", "homeroom"),
        ("2026-09-03", "house"),
    ):
        days[date_key] = {
            "kind": "instructional",
            "schedule_id": schedule_id,
            "label": schedule_id.title(),
        }
    return {
        "version": "1.0-json",
        "type": "SCHOOL_CALENDAR",
        "revision": 1,
        "school_year": "2026-27",
        "coverage": {"start": "2026-09-01", "end": "2026-09-03"},
        "days": days,
        "grading_periods": [],
        "events": [],
    }


def _schedules():
    common = [
        _meeting("1", "8:35 AM", "9:25 AM"),
        _meeting("2", "9:29 AM", "10:21 AM"),
        _meeting("3", "10:25 AM", "11:15 AM"),
        _meeting("4", "11:19 AM", "12:09 PM"),
        _meeting("bobcat_hour", "12:11 PM", "1:13 PM", "Bobcat Hour"),
        _meeting("5", "1:17 PM", "2:07 PM"),
        _meeting("6", "2:11 PM", "3:01 PM"),
        _meeting("7", "3:05 PM", "3:55 PM"),
    ]
    return {
        "bobcat": common[:4] + [
            _meeting("bobcat_hour", "12:11 PM", "1:13 PM", "Bobcat Hour"),
            _meeting("lunch", "12:43 PM", "1:13 PM"),
        ] + common[5:],
        "homeroom": [
            _meeting("1", "8:35 AM", "9:25 AM"),
            _meeting("2", "9:29 AM", "10:19 AM"),
            _meeting("homeroom", "10:23 AM", "10:53 AM", "Homeroom"),
            _meeting("3", "10:57 AM", "11:47 AM"),
            _meeting("4", "11:51 AM", "1:13 PM"),
            _meeting("lunch", "12:38 PM", "1:13 PM"),
            _meeting("5", "1:17 PM", "2:07 PM"),
            _meeting("6", "2:11 PM", "3:01 PM"),
            _meeting("7", "3:05 PM", "3:55 PM"),
        ],
        "house": [
            _meeting("1", "8:35 AM", "9:15 AM"),
            _meeting("2", "9:20 AM", "10:00 AM"),
            _meeting("3", "10:05 AM", "10:45 AM"),
            _meeting("5", "10:50 AM", "11:30 AM"),
            _meeting("4", "11:35 AM", "12:55 PM"),
            _meeting("lunch", "12:20 PM", "12:55 PM"),
            _meeting("6", "1:00 PM", "1:40 PM"),
            _meeting("7", "1:45 PM", "2:25 PM"),
            _meeting("homeroom", "2:30 PM", "3:55 PM", "Homeroom"),
        ],
    }


def _teacher_schedule():
    return {
        "version": "1.0-json",
        "blocks": [
            {"name": "1st", "raw_periods": [1], "label": "FCS", "course_id": "fcs"},
            {"name": "4th/5th", "raw_periods": [4, 5], "label": "ELA 4/5", "course_id": "ela45"},
            {"name": "6th/7th", "raw_periods": [6, 7], "label": "ELA 6/7", "course_id": "ela67"},
        ],
    }


def _context(at):
    return glass.get_current_context(
        at,
        calendar_document=_calendar(),
        bell_schedules=_schedules(),
        teacher_schedule=_teacher_schedule(),
        resolved_at=datetime(2026, 8, 15, 15, tzinfo=timezone.utc),
    )


def test_full_bobcat_homeroom_and_house_days_cross_every_transition():
    cases = {
        "2026-09-01": [
            ("08:34", "before_school"),
            ("08:35", "in_class"),
            ("09:26", "free"),
            ("11:16", "up_next"),
            ("12:30", "free"),
            ("12:50", "lunch"),
            ("13:14", "up_next"),
            ("14:00", "in_class"),
            ("15:56", "after_school"),
        ],
        "2026-09-02": [
            ("11:55", "in_class"),
            ("12:40", "lunch"),
            ("13:14", "up_next"),
        ],
        "2026-09-03": [
            ("11:40", "in_class"),
            ("12:25", "lunch"),
            ("12:56", "up_next"),
            ("14:30", "free"),
            ("15:56", "after_school"),
        ],
    }
    all_seen = set()
    for date_key, checkpoints in cases.items():
        seen = set()
        for clock, expected in checkpoints:
            context = _context(f"{date_key}T{clock}:00")
            assert context["date"] == date_key
            assert context["simulated"] is True
            assert context["valid_until"] > context["at"]
            seen.add(context["state"])
            assert context["state"] == expected, (date_key, clock, context)
        all_seen.update(seen)
    assert {"before_school", "in_class", "up_next", "lunch", "after_school"} <= all_seen

    for date_key in cases:
        for minute in range(24 * 60):
            hour, minute_value = divmod(minute, 60)
            context = _context(f"{date_key}T{hour:02d}:{minute_value:02d}:00")
            assert context["state"] in {
                "before_school", "in_class", "up_next", "lunch", "free", "after_school",
            }
            assert context["mode"] == (
                "class" if context["state"] in {"in_class", "up_next"} else "board"
            )


def test_clock_override_is_normalized_once_and_next_is_populated():
    context = _context("2026-09-01T11:20:00-05:00")

    assert context["at"] == "2026-09-01T11:20:00-05:00"
    assert context["state"] == "in_class"
    assert context["block"]["period_ids"] == ["4"]
    assert context["next"]["name"] == "4th/5th"
    assert context["next"]["starts_at"] == "1:17 PM"
    assert context["valid_until"] == "2026-09-01T12:09:00-05:00"


def test_non_ready_calendar_states_are_board_states():
    document = _calendar()
    document["days"]["2026-09-01"] = {
        "kind": "no_school",
        "schedule_id": None,
        "label": "Labor Day",
    }
    context = glass.get_current_context(
        "2026-09-01T10:00:00-05:00",
        calendar_document=document,
        bell_schedules=_schedules(),
        teacher_schedule=_teacher_schedule(),
    )

    assert context["state"] == "no_school"
    assert context["mode"] == "board"
    assert context["block"] is None
    assert context["next"] is None


def test_glass_module_has_no_canvas_client_import():
    source = open(glass.__file__, encoding="utf-8").read().lower()
    assert "canvas" not in source
