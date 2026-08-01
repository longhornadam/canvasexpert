"""Panels: due-window selection and the states a projector can land in.

Uses the ``catalog_reader`` seam ``read_service`` already exposes rather than
writing any course to disk. Nothing here stands up a fake Canvas; it exercises
the pure selection logic and the empty/error states, which is the half of this
that is observable year-round.
"""
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from api.webui.deck_schedule import resolve_day
from api.webui.routes.panels import (
    DEFAULT_THEME,
    PANEL_THEMES,
    _NO_SCHOOL_DAY_MARKER,
    resolve_panel_course,
    resolve_theme,
    whats_due_payload,
)

NOW = datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc)
THEMES_CSS = (Path(__file__).resolve().parents[2]
              / "api" / "webui" / "static" / "panels" / "themes.css")


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


def _block(name, start, end, course_id="9000001", label=""):
    return {"name": name, "label": label, "start": start, "end": end,
            "course_id": course_id}


def _schedule(blocks, problems=()):
    return lambda _date: (list(blocks), list(problems))


DAY = [
    _block("1st", "08:15", "09:05", "111", label="ELA 7 A"),
    _block("Conference", "09:10", "10:00", ""),
    _block("3rd", "10:05", "10:55", "333", label="ELA 7 B"),
]


def _at(hour, minute):
    return datetime(2026, 8, 17, hour, minute)


def test_an_explicit_course_still_pins_the_panel():
    """A second monitor dedicated to one section must keep working."""
    out = resolve_panel_course("555", now=_at(9, 30), schedule_reader=_schedule(DAY))

    assert out["course_id"] == "555"
    assert out["relation"] == "pinned"
    assert out["state"] == ""


def test_follows_the_block_meeting_right_now():
    out = resolve_panel_course("", now=_at(8, 30), schedule_reader=_schedule(DAY))

    assert out["course_id"] == "111"
    assert out["relation"] == "now"
    assert out["block"] == "ELA 7 A"
    assert out["next_change"] == "09:05"   # re-reads at the bell, not on drift


def test_between_blocks_looks_ahead_to_the_next_one():
    """Passing period. A blank board helps nobody walking in."""
    out = resolve_panel_course("", now=_at(10, 2), schedule_reader=_schedule(DAY))

    assert out["course_id"] == "333"
    assert out["relation"] == "next"
    assert out["next_change"] == "10:05"


def test_before_the_first_bell_shows_the_first_block():
    out = resolve_panel_course("", now=_at(7, 5), schedule_reader=_schedule(DAY))

    assert out["course_id"] == "111"
    assert out["relation"] == "next"


def test_a_block_with_no_canvas_course_is_named_not_errored():
    out = resolve_panel_course("", now=_at(9, 30), schedule_reader=_schedule(DAY))

    assert out["course_id"] == ""
    assert out["state"] == "block_without_course"
    assert "Conference" in out["message"]


def test_after_the_last_block_the_day_is_over():
    out = resolve_panel_course("", now=_at(16, 0), schedule_reader=_schedule(DAY))

    assert out["state"] == "day_over"
    assert out["course_id"] == ""


def test_no_schedule_configured_says_so():
    out = resolve_panel_course("", now=_at(9, 0), schedule_reader=_schedule([]))

    assert out["state"] == "no_schedule"
    assert "schedule" in out["message"].lower()


def test_a_non_school_day_is_not_a_setup_problem():
    """Summer and holidays must not nag a teacher to configure what is fine."""
    reader = _schedule([], problems=["no schedule for 2026-08-17"])
    out = resolve_panel_course("", now=_at(9, 0), schedule_reader=reader)

    assert out["state"] == "not_school_day"


def test_no_school_day_marker_still_matches():
    """resolve_day owns the wording; this panel reads it. If it is reworded
    without updating the marker, every summer day becomes 'set up your
    schedule' instead of 'no classes today'."""
    _blocks, problems = resolve_day("2026-07-04", {}, {}, {"blocks": []})

    assert any(_NO_SCHOOL_DAY_MARKER in p for p in problems)


def test_schedule_failure_never_takes_the_panel_down():
    def explode(_date):
        raise RuntimeError("workspace unavailable")

    out = resolve_panel_course("", now=_at(9, 0), schedule_reader=explode)

    assert out["state"] == "no_schedule"
    assert out["course_id"] == ""


def test_the_data_route_carries_the_schedule_context(monkeypatch):
    """The panel needs block and next_change to label itself and to re-read at
    the bell, so they have to survive the route, not just the resolver."""
    from fastapi.testclient import TestClient
    from api.webui.routes import panels as panels_routes
    from api.webui.server import app

    monkeypatch.setattr(panels_routes.deps, "resolve_schedule_for",
                        _schedule([_block("3rd", "00:00", "23:59", "333",
                                          label="ELA 7 B")]))
    body = TestClient(app, base_url="http://127.0.0.1:8765").get(
        "/panels/whats-due/data").json()

    assert body["ok"] is True
    assert body["relation"] == "now"
    assert body["block"] == "ELA 7 B"
    assert body["next_change"] == "23:59"
    # With no catalog the panel still labels itself from the schedule rather
    # than showing a blank header.
    assert body["course_name"] == "ELA 7 B"


def test_known_themes_resolve_to_themselves():
    for key, _label in PANEL_THEMES:
        assert resolve_theme(key) == key


def test_unknown_theme_falls_back_rather_than_failing():
    """A retired or mistyped theme must not take a saved board down."""
    for value in ("", None, "nope", "  ", "../etc", "CE"):
        assert resolve_theme(value) in {key for key, _ in PANEL_THEMES}
    assert resolve_theme("nope") == DEFAULT_THEME
    assert resolve_theme("  Ocean  ") == "ocean"   # trimmed and lowercased


def test_every_offered_theme_is_actually_styled():
    """The dropdown and the stylesheet are one list in two files. A theme
    offered without a rule block renders an unthemed panel on a wall."""
    css = THEMES_CSS.read_text(encoding="utf-8")
    for key, _label in PANEL_THEMES:
        assert f'html[data-panel-theme="{key}"]' in css, key


def test_themes_never_restyle_the_sizing_model():
    """Row-fitting is measured in JS from the body box. A theme that set a
    box property on a kit element would change how many rows a panel shows,
    so a theme skins .panel and body and touches no other kit class."""
    css = re.sub(r"/\*.*?\*/", "", THEMES_CSS.read_text(encoding="utf-8"), flags=re.S)
    selectors = [block.split("}")[-1].strip() for block in css.split("{")[:-1]]
    off_limits = (".p-row", ".p-body", ".p-head", ".p-foot", ".p-stack", ".p-title")
    offenders = [s for s in selectors if any(hook in s for hook in off_limits)]
    assert offenders == [], offenders
