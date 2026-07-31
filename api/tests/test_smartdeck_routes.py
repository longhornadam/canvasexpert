"""SmartDeck route tests — local-only deck management and readiness."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.webui import deck_store, workspace
from api.webui.routes.smartdeck import _resolve_slides
from api.webui.server import app


client = TestClient(app)


def test_resolve_slides_binds_repeated_block_to_first_meeting():
    slides, problems = _resolve_slides(
        {
            "date": "2026-08-14",
            "slides": [{"id": "x", "block": "ELA 7", "layout": "title_only"}],
        },
        [
            {"name": "ELA 7", "start": "08:35", "end": "10:30"},
            {"name": "ELA 7", "start": "12:40", "end": "15:55"},
        ],
    )
    assert slides[0]["start"] == "08:35"
    assert problems == [
        "slide 'x': block 'ELA 7' also meets 12:40-15:55; "
        "this slide shows at the 08:35 meeting only"
    ]


@pytest.fixture(autouse=True)
def isolated_workspace(tmp_path, monkeypatch):
    """Isolate the workspace to a temporary directory for each test."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(workspace_root))
    monkeypatch.setattr(workspace, "library_folder", lambda name: str(workspace_root / "Library" / name))
    monkeypatch.setattr(workspace, "system_folder", lambda name: str(workspace_root / "_System" / name))
    monkeypatch.setattr(workspace, "path_within_workspace", lambda p: True)  # Allow any path for testing
    return workspace_root


def test_smartdeck_page_get_returns_200_and_html():
    """GET /smartdeck returns 200 and renders the page."""
    response = client.get("/smartdeck")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


def test_smartdeck_page_has_section_rail_and_settings_link():
    text = client.get("/smartdeck").text
    assert "Decks of classroom-display Slides for your projector." not in text
    for panel_id in ("smartdeck-active", "smartdeck-templates", "smartdeck-archived", "smartdeck-widgets"):
        assert f'id="{panel_id}"' in text
        assert f'href="#{panel_id}"' in text
    assert 'href="/settings#class-schedule-card"' in text
    assert "/static/ui/rail_nav.js" in text


def test_smartdeck_api_decks_empty_workspace_returns_empty_lists():
    """GET /smartdeck/api/decks with empty workspace returns ok=True and empty lists."""
    response = client.get("/smartdeck/api/decks")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["active"] == []
    assert data["archived"] == []
    assert data["deck_templates"] == []
    assert data["slide_templates"] == []


def test_smartdeck_api_decks_lists_active_decks(isolated_workspace, monkeypatch):
    """GET /smartdeck/api/decks lists active decks after save."""
    # Save a test deck
    deck_data = {
        "version": "1.0-json",
        "type": "DECK",
        "date": "2026-08-01",
        "title": "Test Deck",
        "slides": [{"id": "slide-1", "block": "Content", "layout": "title_body"}],
    }
    saved_deck, problems = deck_store.save_deck(deck_data)
    assert saved_deck is not None
    assert problems == []

    # Fetch the list
    response = client.get("/smartdeck/api/decks")
    data = response.json()

    assert data["ok"] is True
    assert len(data["active"]) == 1
    assert data["active"][0]["title"] == "Test Deck"
    assert data["active"][0]["date"] == "2026-08-01"


def test_smartdeck_api_decks_archive_moves_deck_to_archived(isolated_workspace):
    """POST /smartdeck/api/decks/{id}/archive moves a deck from active to archived."""
    # Save a deck
    deck_data = {
        "version": "1.0-json",
        "type": "DECK",
        "date": "2026-08-02",
        "title": "To Archive",
        "slides": [{"id": "slide-1", "block": "Content", "layout": "title_body"}],
    }
    saved_deck, _ = deck_store.save_deck(deck_data)
    deck_id = saved_deck["deck_id"]

    # Archive it via the API
    response = client.post(f"/smartdeck/api/decks/{deck_id}/archive")
    result = response.json()
    assert result["ok"] is True
    assert result["problems"] == []

    # Verify it moved to archived
    response = client.get("/smartdeck/api/decks")
    data = response.json()
    assert len(data["active"]) == 0
    assert len(data["archived"]) == 1
    assert data["archived"][0]["deck_id"] == deck_id


def test_smartdeck_api_decks_delete_moves_to_system_archive(isolated_workspace):
    """POST /smartdeck/api/decks/{id}/delete moves deck to _System/Archive/SmartDecks."""
    # Save a deck
    deck_data = {
        "version": "1.0-json",
        "type": "DECK",
        "date": "2026-08-03",
        "title": "To Delete",
        "slides": [{"id": "slide-1", "block": "Content", "layout": "title_body"}],
    }
    saved_deck, _ = deck_store.save_deck(deck_data)
    deck_id = saved_deck["deck_id"]

    # Delete it via the API
    response = client.post(f"/smartdeck/api/decks/{deck_id}/delete")
    result = response.json()
    assert result["ok"] is True
    assert result["problems"] == []

    # Verify it's gone from active and archived
    response = client.get("/smartdeck/api/decks")
    data = response.json()
    assert len(data["active"]) == 0
    assert len(data["archived"]) == 0


def test_smartdeck_api_decks_delete_nonexistent_returns_error():
    """POST /smartdeck/api/decks/{id}/delete for nonexistent id returns ok=False."""
    response = client.post("/smartdeck/api/decks/nonexistent-id/delete")
    result = response.json()
    assert result["ok"] is False
    assert len(result["problems"]) > 0


def test_smartdeck_api_readiness_empty_workspace_returns_not_ready(isolated_workspace):
    """GET /smartdeck/api/readiness with missing schedules returns ready=False."""
    response = client.get("/smartdeck/api/readiness")
    assert response.status_code == 200
    data = response.json()

    assert data["ok"] is True
    assert data["ready"] is False
    assert len(data["missing"]) > 0  # Should list what's missing


def test_smartdeck_api_readiness_returns_problems_list():
    """GET /smartdeck/api/readiness includes problems from all three loaders."""
    response = client.get("/smartdeck/api/readiness")
    data = response.json()

    assert data["ok"] is True
    assert isinstance(data["missing"], list)
    # With empty workspace, we expect problems about missing schedules
    assert any("schedule" in str(p).lower() or "calendar" in str(p).lower()
               for p in data["missing"])


def test_smartdeck_readiness_keeps_ready_and_missing_keys():
    data = client.get("/smartdeck/api/readiness").json()
    assert data["ok"] is True
    assert isinstance(data["ready"], bool)
    assert isinstance(data["missing"], list)


def test_smartdeck_readiness_adds_pieces():
    data = client.get("/smartdeck/api/readiness").json()
    assert set(data["pieces"]) == {"teacher_schedule", "bell_schedules", "day_calendar"}


def test_smartdeck_readiness_names_the_missing_bell_schedules(isolated_workspace):
    calendars = isolated_workspace / "Library" / "Calendars"
    smartdecks = isolated_workspace / "Library" / "SmartDecks"
    calendars.mkdir(parents=True)
    smartdecks.mkdir(parents=True)
    (smartdecks / "Teacher Schedule.json").write_text(
        json.dumps({"blocks": [{"name": "Algebra", "raw_periods": [1]}]}),
        encoding="utf-8",
    )
    (calendars / "Day Calendar.csv").write_text(
        "date,schedule_id\n2026-08-17,missing_bell\n", encoding="utf-8"
    )
    data = client.get("/smartdeck/api/readiness").json()
    assert "no bell schedules found" in data["missing"]
