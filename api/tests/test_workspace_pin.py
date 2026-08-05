"""Regression test for the headless workspace-resolution fix.

The MCP server is launched by Claude Desktop / ChatGPT without the OneDrive
environment variable. Without a persisted workspace_path it could not find the
OneDrive workspace and fell back to stale machine-local state (wrong courses,
no mirror, no identity vault). `config.ensure_workspace_pinned()` persists the
resolved path so every process resolves the same workspace deterministically.
"""
from api.platform_services import config
from api.platform_services.config import canvas


def test_pin_persists_resolved_path_when_unpinned(monkeypatch):
    written = {}
    monkeypatch.setattr(canvas, "get_workspace_path", lambda: None)
    monkeypatch.setattr(canvas.workspace, "workspace_root", lambda: r"C:\ws\CanvasExpert")
    monkeypatch.setattr(canvas, "set_workspace_path", lambda p: written.__setitem__("path", p))

    assert config.ensure_workspace_pinned() == r"C:\ws\CanvasExpert"
    assert written["path"] == r"C:\ws\CanvasExpert"


def test_pin_is_noop_when_already_pinned(monkeypatch):
    written = {}
    monkeypatch.setattr(canvas, "get_workspace_path", lambda: r"C:\already\CanvasExpert")
    monkeypatch.setattr(canvas, "set_workspace_path", lambda p: written.__setitem__("path", p))

    assert config.ensure_workspace_pinned() == r"C:\already\CanvasExpert"
    assert "path" not in written  # never overwrites an existing pin


def test_pin_returns_none_when_nothing_resolves(monkeypatch):
    written = {}
    monkeypatch.setattr(canvas, "get_workspace_path", lambda: None)
    monkeypatch.setattr(canvas.workspace, "workspace_root", lambda: None)
    monkeypatch.setattr(canvas, "set_workspace_path", lambda p: written.__setitem__("path", p))

    assert config.ensure_workspace_pinned() is None
    assert "path" not in written  # nothing to pin on an unconfigured machine
