"""Calendar-only board projections for Glass."""

from datetime import datetime, timezone

from api.webui import glass_board


def _document():
    return {
        "version": "1.0-json",
        "type": "SCHOOL_CALENDAR",
        "revision": 1,
        "school_year": "2026-27",
        "coverage": {"start": "2026-09-01", "end": "2026-09-30"},
        "days": {
            day: {"kind": "instructional", "schedule_id": "ordinary"}
            for day in ("2026-09-01", "2026-09-02", "2026-09-03")
        },
        "grading_periods": [{
            "code": "T1", "name": "Term 1", "start": "2026-09-01",
            "end": "2026-09-10", "report_issue_date": "2026-09-15",
        }],
        "events": [
            {"id": "assembly", "kind": "assembly", "label": "Assembly",
             "shape": "date", "date": "2026-09-02", "detail": "Gym"},
            {"id": "spirit", "kind": "spirit", "label": "Spirit week",
             "shape": "span", "start": "2026-09-02", "end": "2026-09-04"},
            {"id": "tutorial", "kind": "tutorial", "label": "Math help",
             "shape": "date", "date": "2026-09-02", "from": "12:10 PM", "to": "12:35 PM"},
            {"id": "game", "kind": "game", "label": "Bobcats vs Tigers",
             "shape": "date", "date": "2026-09-01", "result": "2–1"},
            {"id": "future-game", "kind": "game", "label": "Future game",
             "shape": "date", "date": "2026-09-05", "result": ""},
        ],
    }


def _schedules():
    return {"ordinary": [
        {"period_id": "bobcat_a", "start": "12:00 PM", "end": "12:35 PM"},
        {"period_id": "bobcat_b", "start": "12:40 PM", "end": "1:15 PM"},
    ]}


def test_board_projects_public_calendar_regions_from_one_document():
    payload = glass_board.get_board_context(
        "2026-09-02T12:15:00-05:00",
        calendar_document=_document(),
        bell_schedules=_schedules(),
        teacher_schedule={"blocks": []},
    )
    board = payload["board"]

    assert payload["context"]["state"] == "free"
    assert [item["label"] for item in board["today_events"]] == [
        "Assembly", "Spirit week", "Math help"
    ]
    assert [item["label"] for item in board["forward_events"]] == ["Spirit week", "Future game"]
    assert board["academic_dates"][0]["label"] == "Term 1 ends"
    assert board["sports_results"][0]["result"] == "2–1"
    assert board["bobcat"]["state"] == "ready"
    assert board["bobcat"]["current_block"] == "A"
    assert board["bobcat"]["activities"][0]["slot"] == "A"
    assert board["grading_period"]["days_remaining"] == 8
    assert "student" not in str(board).lower()


def test_board_keeps_repair_state_without_filling_regions():
    payload = glass_board.get_board_context(
        "2026-09-02T12:15:00-05:00",
        calendar_document=None,
        bell_schedules={},
        teacher_schedule={},
    )

    assert payload["context"]["state"] == "unconfigured"
    assert payload["board"]["state"] == "unconfigured"
    assert payload["board"]["today_events"] == []
    assert payload["board"]["grading_period"]["state"] == "none"
