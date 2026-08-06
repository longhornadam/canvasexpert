"""Tests for the onboarding wizard's workspace step.

Covers the workspace_suggestion fallback rule (never a silent bare home-dir
guess) and the native folder-browse endpoint.
"""
from fastapi.testclient import TestClient

from api.platform_services import config, workspace
from api.webui import server
from api.webui.routes import onboarding


def _client(monkeypatch):
    monkeypatch.setattr(config, "get_canvas_base", lambda: "")
    monkeypatch.setattr(config, "token_is_set", lambda: False)
    return TestClient(server.app)


def test_welcome_suggests_existing_saved_workspace_path(monkeypatch, tmp_path):
    saved = str(tmp_path / "already-configured" / "CanvasExpert")
    monkeypatch.setattr(config, "get_workspace_path", lambda: saved)
    monkeypatch.setattr(workspace, "onedrive_root", lambda: str(tmp_path / "OneDrive"))

    response = _client(monkeypatch).get("/welcome")

    assert response.status_code == 200
    assert f'value="{saved}"' in response.text


def test_welcome_suggests_onedrive_when_no_saved_path(monkeypatch, tmp_path):
    onedrive = str(tmp_path / "OneDrive - District")
    monkeypatch.setattr(config, "get_workspace_path", lambda: "")
    monkeypatch.setattr(workspace, "onedrive_root", lambda: onedrive)

    response = _client(monkeypatch).get("/welcome")

    assert response.status_code == 200
    assert f'value="{onedrive}\\CanvasExpert"' in response.text


def test_welcome_leaves_workspace_empty_when_nothing_found(monkeypatch):
    # No saved path and no OneDrive: must NOT fall back to the bare home
    # directory. A silent guess behind one Confirm click risks putting a
    # teacher's work somewhere with no sync and no backup.
    monkeypatch.setattr(config, "get_workspace_path", lambda: "")
    monkeypatch.setattr(workspace, "onedrive_root", lambda: None)

    response = _client(monkeypatch).get("/welcome")

    assert response.status_code == 200
    assert 'value=""' in response.text
    assert "AppData" not in response.text
    assert "couldn't find OneDrive automatically" in response.text


def test_browse_workspace_returns_chosen_path(monkeypatch):
    monkeypatch.setattr(onboarding, "_ask_directory", lambda: r"C:\Teachers\Documents\CanvasExpert")

    response = TestClient(server.app).post("/welcome/browse-workspace")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "path": r"C:\Teachers\Documents\CanvasExpert"}


def test_browse_workspace_returns_null_path_on_cancel(monkeypatch):
    monkeypatch.setattr(onboarding, "_ask_directory", lambda: "")

    response = TestClient(server.app).post("/welcome/browse-workspace")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "path": None}


def test_browse_workspace_reports_error_when_dialog_unavailable(monkeypatch):
    def _boom():
        raise RuntimeError("no display available")

    monkeypatch.setattr(onboarding, "_ask_directory", _boom)

    response = TestClient(server.app).post("/welcome/browse-workspace")

    assert response.status_code == 200
    assert response.json() == {"ok": False, "path": None, "error": "no_dialog_available"}
