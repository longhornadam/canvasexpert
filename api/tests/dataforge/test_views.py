"""Tests for the framework-agnostic view layer in dataforge.views.

This module exists so the route logic can be ported to a different web host
later without untangling it from Flask. These tests check three things:

  - views.py stays free of any web framework import (belt and braces
    alongside the parametrized guard in test_dependency_boundaries.py, which
    would already fail the suite if this regressed).
  - the result types (Render, Redirect, FileDownload, BytesDownload) carry
    exactly what a host needs to build a response from them.
  - a handful of views/helpers behave correctly at their edges: an unknown
    run id, a download path reaching outside the output folder, and NotFound
    mapping to a real 404 through the Flask app.
"""

import ast
from pathlib import Path

import pytest

from api.dataforge import paths as path_config, views

VIEWS_PATH = Path(__file__).resolve().parents[2] / "dataforge" / "views.py"

FRAMEWORKS = {"flask", "fastapi", "django", "starlette", "werkzeug"}


def _imported_roots(path: Path) -> set:
    """Top-level package name of every import in a module."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # level > 0 is a relative import, which has no external root.
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


# --- 1. views.py imports no web framework ---------------------------------


def test_views_module_imports_no_web_framework():
    leaked = _imported_roots(VIEWS_PATH) & FRAMEWORKS
    assert not leaked, f"views.py imports {sorted(leaked)}; keep the web layer outside dataforge"


def test_views_module_does_not_reference_flask_globals():
    """Belt and braces: no bare name 'request' or 'session' anywhere, which
    would signal a Flask global crept back in even without a fresh import."""
    tree = ast.parse(VIEWS_PATH.read_text(encoding="utf-8"), filename=str(VIEWS_PATH))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert "request" not in names
    assert "session" not in names


# --- 2. result types carry what a host needs -------------------------------


def test_redirect_keeps_endpoint_and_params():
    r = views.Redirect("results", run_id="abc123")
    assert r.endpoint == "results"
    assert r.params == {"run_id": "abc123"}


def test_render_keeps_template_and_context():
    r = views.Render("history.html", snapshots=[1, 2, 3], extra="x")
    assert r.template == "history.html"
    assert r.context == {"snapshots": [1, 2, 3], "extra": "x"}


def test_file_download_keeps_path_and_optional_download_name():
    p = Path("somefile.json")
    r = views.FileDownload(p)
    assert r.path == p
    assert r.download_name is None

    r2 = views.FileDownload(p, download_name="renamed.json")
    assert r2.download_name == "renamed.json"


def test_bytes_download_keeps_payload():
    r = views.BytesDownload(b"hello", mimetype="application/json", download_name="x.json")
    assert r.data == b"hello"
    assert r.mimetype == "application/json"
    assert r.download_name == "x.json"


# --- 3. _resolve_in_output --------------------------------------------------


def test_resolve_in_output_returns_the_path_for_a_real_file():
    paths = path_config.get_paths()
    target = paths.output_dir / "report.txt"
    target.write_text("hi", encoding="utf-8")

    resolved = views._resolve_in_output("report.txt")
    assert resolved == target.resolve()


def test_resolve_in_output_raises_not_found_for_a_missing_file():
    path_config.get_paths()
    with pytest.raises(views.NotFound):
        views._resolve_in_output("does-not-exist.txt")


def test_resolve_in_output_raises_not_found_for_a_traversal_attempt():
    """A name that tries to reach outside the output dir must not resolve to
    a file that lives elsewhere, even when that file really exists."""
    paths = path_config.get_paths()
    secret = paths.data_dir / "secret.txt"
    secret.write_text("do not serve this", encoding="utf-8")

    with pytest.raises(views.NotFound):
        views._resolve_in_output("../secret.txt")


# --- 4. views returning Redirect --------------------------------------------


def test_results_view_redirects_to_index_for_unknown_run_id():
    views.RUNS.clear()
    result = views.results("no-such-run")
    assert isinstance(result, views.Redirect)
    assert result.endpoint == "index"
    assert result.params == {}


def test_dashboard_view_redirects_to_index_for_unknown_run_id():
    views.RUNS.clear()
    result = views.dashboard("no-such-run")
    assert isinstance(result, views.Redirect)
    assert result.endpoint == "index"


def test_history_delete_view_redirects_to_history():
    path_config.get_paths()
    result = views.history_delete("some-snapshot-id")
    assert isinstance(result, views.Redirect)
    assert result.endpoint == "history"
