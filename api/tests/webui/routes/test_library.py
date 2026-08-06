"""Route coverage for the AI-TA (AI Authoring) file and toolkit-file downloads.

Both routes read one flat file by basename and, since the Content-Disposition
fix landed, must return a header carrying the real filename -- not the bare
route name the browser used to fall back to. Covers a name with spaces and
parentheses, a non-ASCII name (the RFC 5987 filename* form), and proves the
existing traversal/404 guards still hold unchanged.
"""
import pytest
from fastapi.testclient import TestClient

from api import runtime_paths
from api.webui import server

_ROUTES = ("/api/ai-ta/file", "/api/ai-ta/toolkit-file")


def _client():
    return TestClient(server.app, base_url="http://127.0.0.1:8765")


def _serve_from(monkeypatch, tmp_path, route):
    """Point runtime_paths.ai_ta_dir() at an empty tmp directory and return
    the directory the given route actually reads files from."""
    ai_ta_dir = tmp_path / "AI Authoring"
    ai_ta_dir.mkdir()
    monkeypatch.setattr(runtime_paths, "ai_ta_dir", lambda: ai_ta_dir)
    if route == "/api/ai-ta/toolkit-file":
        toolkit_dir = ai_ta_dir / "MagicSchool Toolkit"
        toolkit_dir.mkdir()
        return toolkit_dir
    return ai_ta_dir


@pytest.mark.parametrize("route", _ROUTES)
def test_download_carries_the_real_filename_with_spaces_and_parens(monkeypatch, tmp_path, route):
    directory = _serve_from(monkeypatch, tmp_path, route)
    name = "Author a Quiz (QuizForge).txt"
    (directory / name).write_text("quiz forge contract", encoding="utf-8")

    response = _client().get(route, params={"name": name})

    assert response.status_code == 200
    assert response.text == "quiz forge contract"
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert response.headers["content-disposition"] == (
        'attachment; filename="Author a Quiz (QuizForge).txt"; '
        "filename*=UTF-8''Author%20a%20Quiz%20%28QuizForge%29.txt"
    )


@pytest.mark.parametrize("route", _ROUTES)
def test_download_non_ascii_name_emits_the_rfc5987_form(monkeypatch, tmp_path, route):
    directory = _serve_from(monkeypatch, tmp_path, route)
    name = "Ünïcode Café.txt"
    (directory / name).write_text("accented contract", encoding="utf-8")

    response = _client().get(route, params={"name": name})

    assert response.status_code == 200
    assert response.text == "accented contract"
    disposition = response.headers["content-disposition"]
    assert "filename*=UTF-8''%C3%9Cn%C3%AFcode%20Caf%C3%A9.txt" in disposition
    # The plain filename parameter is the fallback for clients that do not
    # understand filename* -- it must stay ASCII (Starlette encodes header
    # values as Latin-1, so raw multi-byte characters there would crash the
    # response) rather than carry the real bytes.
    assert 'filename="?n?code Caf?.txt"' in disposition


@pytest.mark.parametrize("route", _ROUTES)
def test_download_still_rejects_traversal(monkeypatch, tmp_path, route):
    _serve_from(monkeypatch, tmp_path, route)

    response = _client().get(route, params={"name": "../secret.txt"})

    assert response.status_code == 400
    assert response.json() == {"error": "invalid name"}


@pytest.mark.parametrize("route", _ROUTES)
def test_download_still_404s_on_a_missing_file(monkeypatch, tmp_path, route):
    _serve_from(monkeypatch, tmp_path, route)

    response = _client().get(route, params={"name": "does-not-exist.txt"})

    assert response.status_code == 404
    assert response.json() == {"error": "file not found"}
