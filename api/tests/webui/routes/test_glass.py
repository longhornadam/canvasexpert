"""Rendered Glass route contract."""

from pathlib import Path

from fastapi.testclient import TestClient

from api.platform_services import config
from api.webui.routes import glass as glass_routes
from api.webui.server import app


client = TestClient(app)


def test_glass_page_loads_display_template_once(monkeypatch):
    monkeypatch.setattr(config, "token_is_set", lambda: True)
    monkeypatch.setattr(config, "get_canvas_base", lambda: "https://canvas.invalid")
    monkeypatch.setattr(glass_routes.glass_board, "get_board_context", lambda at=None: {
        "context": {"at": "2026-09-02T12:15:00-05:00", "date": "2026-09-02", "simulated": True, "state": "free", "valid_until": "2026-09-02T12:16:00-05:00", "schedule_id": "ordinary"},
        "board": {"state": "free", "schedule_label": "Ordinary", "message": "", "today_events": [], "forward_events": [], "academic_dates": [], "sports_results": [], "bobcat": {"activities": []}, "grading_period": {"state": "none"}},
    })

    response = client.get("/glass?at=2026-09-02T12:15:00-05:00")

    assert response.status_code == 200
    assert "class=\"glass-frame\"" in response.text
    assert response.text.count("/static/pages/glass.js") == 1
    assert "SIMULATED" in response.text
    assert "ce-app-header" not in response.text


def test_glass_data_honors_simulated_clock(monkeypatch):
    calls = []

    def fake_context(at=None):
        calls.append(at)
        return {"context": {"at": at or "real", "state": "free"}, "board": {}}

    monkeypatch.setattr(glass_routes.glass_board, "get_board_context", fake_context)

    response = client.get("/glass/data?at=2026-09-02T12:15:00-05:00")

    assert response.status_code == 200
    assert calls == ["2026-09-02T12:15:00-05:00"]


def test_glass_browser_clock_starts_from_server_timestamp():
    source = (Path(__file__).resolve().parents[3]
              / "webui" / "static" / "pages" / "glass.js").read_text(encoding="utf-8")

    assert "Date.now()" not in source
    assert "new Date()" not in source
    assert "Date.parse(context.at" in source
    template = (Path(__file__).resolve().parents[3]
                / "webui" / "templates" / "glass.html").read_text(encoding="utf-8")
    assert "Random Name" in template
