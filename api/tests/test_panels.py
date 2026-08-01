"""Panels: due-window selection and the states a projector can land in.

Uses the ``catalog_reader`` seam ``read_service`` already exposes rather than
writing any course to disk. Nothing here stands up a fake Canvas; it exercises
the pure selection logic and the empty/error states, which is the half of this
that is observable year-round.
"""
from datetime import datetime, timedelta, timezone

from api.webui.routes.panels import whats_due_payload

NOW = datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc)


def _catalog(records, *, state="current"):
    """A reader returning one course catalog holding ``records``."""
    return lambda _course_id: {
        "catalog": {
            "course_id": "123",
            "course_name": "ELA 7",
            "version": 1,
            "assignments": {
                "state": state,
                "last_success_at": "2026-08-17T08:00:00+00:00",
                "records": records,
            },
        }
    }


def _assignment(name, due, *, published=True, points=10):
    return {"id": name, "name": name, "due_at": due,
            "published": published, "points_possible": points}


def test_selects_only_assignments_inside_the_window():
    reader = _catalog([
        _assignment("yesterday", "2026-08-16T23:00:00Z"),
        _assignment("today",     "2026-08-17T18:00:00Z"),
        _assignment("in 3 days", "2026-08-20T18:00:00Z"),
        _assignment("in 30 days", "2026-09-16T18:00:00Z"),
    ])
    out = whats_due_payload("123", 7, now=NOW, catalog_reader=reader)

    assert out["state"] == "ready"
    assert [a["title"] for a in out["assignments"]] == ["today", "in 3 days"]


def test_sorted_soonest_first_regardless_of_catalog_order():
    reader = _catalog([
        _assignment("later",   "2026-08-21T18:00:00Z"),
        _assignment("sooner",  "2026-08-18T18:00:00Z"),
        _assignment("soonest", "2026-08-17T12:00:00Z"),
    ])
    out = whats_due_payload("123", 7, now=NOW, catalog_reader=reader)

    assert [a["title"] for a in out["assignments"]] == ["soonest", "sooner", "later"]


def test_unpublished_and_undated_assignments_are_not_due():
    reader = _catalog([
        _assignment("draft", "2026-08-18T18:00:00Z", published=False),
        _assignment("no due date", ""),
        _assignment("garbled", "not a date"),
        _assignment("real", "2026-08-18T18:00:00Z"),
    ])
    out = whats_due_payload("123", 7, now=NOW, catalog_reader=reader)

    assert [a["title"] for a in out["assignments"]] == ["real"]


def test_naive_due_dates_are_read_as_utc_rather_than_dropped():
    reader = _catalog([_assignment("naive", "2026-08-18T18:00:00")])
    out = whats_due_payload("123", 7, now=NOW, catalog_reader=reader)

    assert [a["title"] for a in out["assignments"]] == ["naive"]


def test_no_course_selected_is_a_calm_state_not_an_error():
    out = whats_due_payload("", 7, now=NOW, catalog_reader=_catalog([]))

    assert out["ok"] is True
    assert out["state"] == "no_course"
    assert out["assignments"] == []
    assert out["message"]


def test_missing_catalog_tells_the_teacher_what_to_do():
    out = whats_due_payload("123", 7, now=NOW,
                            catalog_reader=lambda _cid: {"catalog": None})

    assert out["ok"] is True
    assert out["state"] == "no_catalog"
    assert "efresh" in out["message"]


def test_empty_window_is_nothing_due_not_no_catalog():
    reader = _catalog([_assignment("far off", "2026-12-01T18:00:00Z")])
    out = whats_due_payload("123", 7, now=NOW, catalog_reader=reader)

    assert out["state"] == "nothing_due"
    assert "next 7 days" in out["message"]


def test_stale_catalog_still_serves_but_is_flagged():
    reader = _catalog([_assignment("today", "2026-08-17T18:00:00Z")],
                      state="stale")
    out = whats_due_payload("123", 7, now=NOW, catalog_reader=reader)

    assert out["state"] == "ready"
    assert out["stale"] is True


def test_lookahead_is_clamped_so_a_hand_edited_url_cannot_ask_for_a_year():
    reader = _catalog([_assignment("way out", "2027-01-01T18:00:00Z")])
    out = whats_due_payload("123", 9999, now=NOW, catalog_reader=reader)

    assert out["days"] == 31
    assert out["assignments"] == []


def test_never_reaches_canvas():
    """A Panel that phoned home would put network failures on a projector."""
    called = []

    def reader(course_id):
        called.append(course_id)
        return _catalog([])(course_id)

    whats_due_payload("123", 7, now=NOW, catalog_reader=reader)
    assert called == ["123", "123"]   # catalog read + scope read, both local
