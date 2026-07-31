"""SmartDeck display page tests — route, payload, and interaction.

Tests the display page (/smartdeck/display/{deck_id}) and its data endpoint
(/smartdeck/display/{deck_id}/data) that serves the complete resolved payload
for the classroom projector.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.webui import deck_store, deps, workspace
from api.webui.server import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_workspace(tmp_path, monkeypatch):
    """Isolate the workspace to a temporary directory for each test."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(workspace_root))
    monkeypatch.setattr(workspace, "library_folder", lambda name: str(workspace_root / "Library" / name))
    monkeypatch.setattr(workspace, "system_folder", lambda name: str(workspace_root / "_System" / name))
    monkeypatch.setattr(workspace, "path_within_workspace", lambda p: True)
    return workspace_root


@pytest.fixture
def schedule_fixture(isolated_workspace):
    """Set up a complete Teacher Schedule + Bell Schedule + Day Calendar."""
    workspace_root = isolated_workspace
    smartdecks_dir = workspace_root / "Library" / "SmartDecks"
    smartdecks_dir.mkdir(parents=True, exist_ok=True)

    calendars_dir = workspace_root / "Library" / "Calendars"
    calendars_dir.mkdir(parents=True, exist_ok=True)

    # Bell schedule CSV
    bell_schedule_content = "period_id,start,end\n1,08:35,09:25\n2,09:29,10:21\n3,10:25,11:17\n4,11:21,12:13\n5,12:13,13:05\n6,13:09,14:01\n7,14:05,14:57\n"
    (calendars_dir / "Bell Schedule.csv").write_text(bell_schedule_content, encoding="utf-8")

    # Day calendar CSV (map dates to bell schedules)
    day_calendar_content = "date,schedule_id\n2026-08-19,bell_schedule\n"
    (calendars_dir / "Day Calendar.csv").write_text(day_calendar_content, encoding="utf-8")

    # Teacher schedule JSON
    teacher_schedule_content = json.dumps({
        "version": "1.0-json",
        "blocks": [
            {"name": "1st Period", "raw_periods": [1], "label": "ELA"},
            {"name": "2nd Period", "raw_periods": [2], "label": "Math"},
            {"name": "3rd Period", "raw_periods": [3], "label": "Science"},
        ]
    })
    (smartdecks_dir / "Teacher Schedule.json").write_text(teacher_schedule_content, encoding="utf-8")

    return smartdecks_dir


def test_smartdeck_display_page_returns_html(isolated_workspace, schedule_fixture):
    """GET /smartdeck/display/{deck_id} returns 200 and HTML."""
    # Create a simple deck
    deck_data = {
        "version": "1.0-json",
        "type": "DECK",
        "date": "2026-08-19",
        "title": "Test Deck",
        "widgets": [
            {"id": "widget-1", "scope": "deck", "kind": "timer", "params": {"duration_seconds": 60, "autostart": False}}
        ],
        "slides": [
            {
                "id": "slide-1",
                "block": "1st Period",
                "layout": "title_body",
                "title": "Slide 1",
                "body": "Content here",
                "widgets": ["widget-1"],
            }
        ],
    }
    saved, _ = deck_store.save_deck(deck_data)
    deck_id = saved["deck_id"]

    response = client.get(f"/smartdeck/display/{deck_id}")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert deck_id in response.text  # deck_id should be in data attribute


def test_smartdeck_display_data_returns_json_payload(isolated_workspace, schedule_fixture):
    """GET /smartdeck/display/{deck_id}/data returns the full payload."""
    deck_data = {
        "version": "1.0-json",
        "type": "DECK",
        "date": "2026-08-19",
        "title": "Test Deck",
        "widgets": [
            {"id": "widget-1", "scope": "deck", "kind": "timer", "params": {"duration_seconds": 60, "label": "Timer"}}
        ],
        "slides": [
            {
                "id": "slide-1",
                "block": "1st Period",
                "layout": "title_body",
                "title": "Slide 1",
                "body": "Content for slide 1",
                "widgets": ["widget-1"],
            },
            {
                "id": "slide-2",
                "block": "2nd Period",
                "layout": "bulleted",
                "title": "Slide 2",
                "body": "Item 1\nItem 2\nItem 3",
                "widgets": [],
            },
        ],
    }
    saved, _ = deck_store.save_deck(deck_data)
    deck_id = saved["deck_id"]

    response = client.get(f"/smartdeck/display/{deck_id}/data")
    assert response.status_code == 200

    data = response.json()
    assert data["ok"] is True
    assert data["deck_id"] == deck_id
    assert data["date"] == "2026-08-19"
    assert data["title"] == "Test Deck"
    assert "server_time" in data
    assert len(data["slides"]) == 2

    # Check slide 1
    slide1 = data["slides"][0]
    assert slide1["id"] == "slide-1"
    assert slide1["block"] == "1st Period"
    assert slide1["layout"] == "title_body"
    assert slide1["title"] == "Slide 1"
    assert slide1["body"] == "Content for slide 1"
    assert slide1["start"] == "08:35"
    assert slide1["end"] == "09:25"

    # Check that slide widgets contain full objects (not bare ids)
    assert len(slide1["widgets"]) == 1
    widget = slide1["widgets"][0]
    assert widget["id"] == "widget-1"
    assert widget["scope"] == "deck"
    assert widget["kind"] == "timer"
    assert widget["params"]["duration_seconds"] == 60
    assert widget["params"]["label"] == "Timer"

    # Check slide 2
    slide2 = data["slides"][1]
    assert slide2["id"] == "slide-2"
    assert slide2["block"] == "2nd Period"
    assert slide2["start"] == "09:29"
    assert slide2["end"] == "10:21"
    assert len(slide2["widgets"]) == 0


def test_smartdeck_display_data_unresolved_block_marked_with_null(isolated_workspace, schedule_fixture):
    """Slide with unresolved block name has null start/end and problem reported."""
    deck_data = {
        "version": "1.0-json",
        "type": "DECK",
        "date": "2026-08-19",
        "title": "Test Deck",
        "widgets": [],
        "slides": [
            {
                "id": "slide-1",
                "block": "NonExistentBlock",
                "layout": "title_body",
                "title": "Unresolved Slide",
                "body": "This block doesn't exist",
                "widgets": [],
            }
        ],
    }
    saved, _ = deck_store.save_deck(deck_data)
    deck_id = saved["deck_id"]

    response = client.get(f"/smartdeck/display/{deck_id}/data")
    assert response.status_code == 200

    data = response.json()
    assert data["ok"] is True

    slide = data["slides"][0]
    assert slide["start"] is None
    assert slide["end"] is None

    # Check that a problem was recorded
    assert len(data["problems"]) > 0
    problem_text = " ".join(data["problems"])
    assert "NonExistentBlock" in problem_text


def test_smartdeck_display_data_slide_with_no_widgets(isolated_workspace, schedule_fixture):
    """Slide with empty widgets array is valid and shows no widgets."""
    deck_data = {
        "version": "1.0-json",
        "type": "DECK",
        "date": "2026-08-19",
        "title": "Test Deck",
        "widgets": [
            {"id": "widget-1", "scope": "slide", "kind": "timer", "params": {"duration_seconds": 60}}
        ],
        "slides": [
            {
                "id": "slide-1",
                "block": "1st Period",
                "layout": "title_body",
                "title": "Slide 1",
                "body": "Content",
                "widgets": [],  # No widgets for this slide
            }
        ],
    }
    saved, _ = deck_store.save_deck(deck_data)
    deck_id = saved["deck_id"]

    response = client.get(f"/smartdeck/display/{deck_id}/data")
    assert response.status_code == 200

    data = response.json()
    slide = data["slides"][0]
    # Should have no widgets
    assert len(slide["widgets"]) == 0


def test_smartdeck_display_data_nonexistent_deck_returns_404(isolated_workspace, schedule_fixture):
    """GET /smartdeck/display/{deck_id}/data for nonexistent deck returns 404."""
    response = client.get("/smartdeck/display/nonexistent-deck-id/data")
    assert response.status_code == 404

    data = response.json()
    assert data["ok"] is False
    assert len(data["problems"]) > 0


def test_smartdeck_display_page_nonexistent_deck_still_loads_page(isolated_workspace, schedule_fixture):
    """GET /smartdeck/display/{deck_id} (HTML page) loads for any deck_id; JS handles 404."""
    # This is correct behavior: the page template loads, the JS fetches the data,
    # and if it's 404, the JS shows an error message.
    response = client.get("/smartdeck/display/nonexistent-deck-id")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


def test_smartdeck_display_data_multiple_slides_same_block(isolated_workspace, schedule_fixture):
    """Multiple slides can share the same block; all get the same start/end."""
    deck_data = {
        "version": "1.0-json",
        "type": "DECK",
        "date": "2026-08-19",
        "title": "Test Deck",
        "widgets": [],
        "slides": [
            {
                "id": "slide-1a",
                "block": "1st Period",
                "layout": "title_body",
                "title": "Slide 1a",
                "body": "First half",
                "widgets": [],
            },
            {
                "id": "slide-1b",
                "block": "1st Period",
                "layout": "title_body",
                "title": "Slide 1b",
                "body": "Second half",
                "widgets": [],
            },
        ],
    }
    saved, _ = deck_store.save_deck(deck_data)
    deck_id = saved["deck_id"]

    response = client.get(f"/smartdeck/display/{deck_id}/data")
    assert response.status_code == 200

    data = response.json()
    slide1a = data["slides"][0]
    slide1b = data["slides"][1]

    assert slide1a["start"] == "08:35"
    assert slide1a["end"] == "09:25"
    assert slide1b["start"] == "08:35"
    assert slide1b["end"] == "09:25"


def test_smartdeck_display_data_includes_schedule_problems(isolated_workspace, schedule_fixture):
    """Problems from schedule resolution (missing schedules, etc.) are included."""
    # Save a deck with a date that isn't in the day calendar
    deck_data = {
        "version": "1.0-json",
        "type": "DECK",
        "date": "2026-12-25",  # Not in day calendar
        "title": "Christmas Deck",
        "widgets": [],
        "slides": [
            {
                "id": "slide-1",
                "block": "1st Period",
                "layout": "title_body",
                "title": "Holiday Slide",
                "body": "Content",
                "widgets": [],
            }
        ],
    }
    saved, _ = deck_store.save_deck(deck_data)
    deck_id = saved["deck_id"]

    response = client.get(f"/smartdeck/display/{deck_id}/data")
    assert response.status_code == 200

    data = response.json()
    assert data["ok"] is True
    # Should have problems about the missing date
    assert len(data["problems"]) > 0
    problem_text = " ".join(data["problems"])
    assert "2026-12-25" in problem_text or "no schedule" in problem_text.lower()


def test_smartdeck_display_data_deck_scope_vs_slide_scope_widgets(isolated_workspace, schedule_fixture):
    """Deck-scoped and slide-scoped widgets are correctly identified in payload."""
    deck_data = {
        "version": "1.0-json",
        "type": "DECK",
        "date": "2026-08-19",
        "title": "Widget Test",
        "widgets": [
            {"id": "deck-timer", "scope": "deck", "kind": "timer", "params": {"duration_seconds": 120}},
            {"id": "slide-timer", "scope": "slide", "kind": "timer", "params": {"duration_seconds": 60}},
        ],
        "slides": [
            {
                "id": "slide-1",
                "block": "1st Period",
                "layout": "title_body",
                "title": "Slide 1",
                "body": "Content",
                "widgets": ["deck-timer", "slide-timer"],
            }
        ],
    }
    saved, _ = deck_store.save_deck(deck_data)
    deck_id = saved["deck_id"]

    response = client.get(f"/smartdeck/display/{deck_id}/data")
    assert response.status_code == 200

    data = response.json()
    slide = data["slides"][0]
    widgets = slide["widgets"]

    # Both should be in the slide's widgets array
    assert len(widgets) == 2
    deck_timer = next((w for w in widgets if w["id"] == "deck-timer"), None)
    slide_timer = next((w for w in widgets if w["id"] == "slide-timer"), None)

    assert deck_timer is not None
    assert deck_timer["scope"] == "deck"
    assert slide_timer is not None
    assert slide_timer["scope"] == "slide"


def test_smartdeck_display_data_server_time_is_iso_format(isolated_workspace, schedule_fixture):
    """server_time is ISO 8601 format."""
    deck_data = {
        "version": "1.0-json",
        "type": "DECK",
        "date": "2026-08-19",
        "title": "Test",
        "widgets": [],
        "slides": [
            {
                "id": "slide-1",
                "block": "1st Period",
                "layout": "title_only",
                "title": "Test Slide",
                "widgets": [],
            }
        ],
    }
    saved, _ = deck_store.save_deck(deck_data)
    deck_id = saved["deck_id"]

    response = client.get(f"/smartdeck/display/{deck_id}/data")
    data = response.json()

    server_time = data["server_time"]
    # Should be parseable as ISO 8601
    from datetime import datetime
    dt = datetime.fromisoformat(server_time)
    assert dt is not None


def _write_raw_deck(smartdecks_dir, deck_id, deck):
    """Drop a deck straight onto disk, bypassing save_deck's validation.

    Models a hand-edited file, which the archive recovery path invites. save_deck would
    reject all of these, so they can only reach the display route this way.
    """
    decks_dir = Path(smartdecks_dir) / "Decks"
    decks_dir.mkdir(parents=True, exist_ok=True)
    (decks_dir / f"{deck_id}.json").write_text(json.dumps(deck), encoding="utf-8")


def _raw_deck(slides):
    return {
        "version": "1.0-json", "type": "DECK", "date": "2026-08-19",
        "title": "Hand Edited", "widgets": [], "slides": slides,
    }


def test_display_data_skips_slide_with_no_id(isolated_workspace, schedule_fixture):
    """A slide with no id is dropped with a problem, not a 500.

    display.js identifies slides by id, so serving one with a null id would make two
    such slides indistinguishable and wedge the rotation.
    """
    _write_raw_deck(schedule_fixture, "2026-08-19.r1", _raw_deck([
        {"block": "1st Period", "layout": "title_only", "title": "No id"},
        {"id": "good", "block": "2nd Period", "layout": "title_only", "title": "Fine"},
    ]))

    response = client.get("/smartdeck/display/2026-08-19.r1/data")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert [s["id"] for s in data["slides"]] == ["good"]
    assert any("has no id" in p for p in data["problems"])


def test_display_data_keeps_only_the_first_of_duplicate_slide_ids(isolated_workspace, schedule_fixture):
    """Duplicate ids break the same identity check, so later copies are dropped."""
    _write_raw_deck(schedule_fixture, "2026-08-19.r1", _raw_deck([
        {"id": "dup", "block": "1st Period", "layout": "title_only", "title": "First"},
        {"id": "dup", "block": "2nd Period", "layout": "title_only", "title": "Second"},
    ]))

    data = client.get("/smartdeck/display/2026-08-19.r1/data").json()
    assert [s["title"] for s in data["slides"]] == ["First"]
    assert any("more than once" in p for p in data["problems"])


def test_display_data_skips_a_slide_that_is_not_an_object(isolated_workspace, schedule_fixture):
    """A malformed entry degrades to a problem rather than an exception."""
    _write_raw_deck(schedule_fixture, "2026-08-19.r1", _raw_deck([
        "not a slide",
        {"id": "good", "block": "1st Period", "layout": "title_only", "title": "Fine"},
    ]))

    data = client.get("/smartdeck/display/2026-08-19.r1/data").json()
    assert [s["id"] for s in data["slides"]] == ["good"]
    assert any("not a slide object" in p for p in data["problems"])


def test_deck_list_reports_problems_for_active_decks(isolated_workspace, schedule_fixture):
    """The management page gets the warning so the teacher sees it before projecting."""
    deck_data = {
        "version": "1.0-json", "type": "DECK", "date": "2026-08-19", "title": "Has a gap",
        "slides": [
            {"id": "s1", "block": "1st Period", "layout": "title_only", "title": "Fine"},
            {"id": "s2", "block": "Nonexistent Block", "layout": "title_only", "title": "Ghost"},
        ],
    }
    saved, problems = deck_store.save_deck(deck_data)
    assert problems == []

    listing = client.get("/smartdeck/api/decks").json()
    entry = next(d for d in listing["active"] if d["deck_id"] == saved["deck_id"])
    assert any("Nonexistent Block" in p for p in entry["problems"])
    assert any("will not appear" in p for p in entry["problems"])


def test_deck_list_reports_no_problems_for_a_clean_deck(isolated_workspace, schedule_fixture):
    """A deck whose blocks all resolve carries an empty problems list."""
    saved, problems = deck_store.save_deck({
        "version": "1.0-json", "type": "DECK", "date": "2026-08-19", "title": "Clean",
        "slides": [{"id": "s1", "block": "1st Period", "layout": "title_only", "title": "Fine"}],
    })
    assert problems == []

    listing = client.get("/smartdeck/api/decks").json()
    entry = next(d for d in listing["active"] if d["deck_id"] == saved["deck_id"])
    assert entry["problems"] == []
