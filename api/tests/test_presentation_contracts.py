"""Architecture and rendered contracts for the staged WebUI presentation system."""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from api.webui.server import app
from api.webui.routes import pages, powergrader


ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "api" / "webui" / "templates"

# Route -> (page template, layout, variant, real rail count, migrated).
EXPECTED_PRESENTATION = {
    "/": ("dashboard.html", "workspace", "full", 0, True),
    "/course-expert": ("course_expert.html", "workspace", "three", 2, True),
    "/powergrader": ("powergrader_setup.html", "workspace", "full", 0, True),
    "/powergrader/session/{session_id}": ("powergrader_queue.html", "workspace", "full", 0, True),
    "/gradebook": ("gradebook.html", "workspace", "left-main", 1, False),
    "/roster": ("roster.html", "workspace", "left-main", 1, False),
    "/settings": ("settings.html", "workspace", "left-main", 1, False),
    "/routines": ("routines.html", "document", "wide", 0, False),
    "/students/reports": ("student_reports.html", "document", "wide", 0, False),
    "/course": ("course.html", "document", "wide", 0, False),
    "/about": ("about.html", "document", "wide", 0, False),
    "/ai-expert": ("ai_expert.html", "document", "standard", 0, False),
    "/welcome": ("welcome.html", "wizard", "", 0, False),
}

MIGRATED_ROUTES = {
    route: row for route, row in EXPECTED_PRESENTATION.items() if row[4]
}
FEATURE_CSS = (
    "api/webui/static/pages/dashboard.css",
    "api/webui/static/pages/course_expert.css",
    "api/webui/static/powergrader_setup.css",
    "api/webui/static/powergrader_queue.css",
)
VISUAL_LITERAL_RE = re.compile(r"font-family:|#[0-9a-fA-F]{3,8}|rgb\(|hsl\(|border-radius:|box-shadow:")
FORBIDDEN_JS_SELECTORS = (
    ".ce-shell", ".ce-panel", ".ce-rail", ".ce-page-header", ".ce-btn",
    ".ce-field", ".ce-tabs", ".ce-notice", ".ce-actions", ".ce-table",
    ".ce-status-dot", ".ce-empty",
)


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _client() -> TestClient:
    return TestClient(app, base_url="http://127.0.0.1:8765")


def _configure_fictional(monkeypatch):
    courses = [{"id": "course-1", "name": "Fictional Course", "nickname": "Fictional", "active": True}]
    monkeypatch.setattr(pages.config, "token_is_set", lambda: True)
    monkeypatch.setattr(pages.config, "get_canvas_base", lambda: "https://canvas.example.test")
    monkeypatch.setattr(pages.config, "active_courses", lambda: courses)
    monkeypatch.setattr(pages.workspace, "workspace_root", lambda: None)
    monkeypatch.setattr(pages.work_routes, "_section_jobs", lambda section: [])
    monkeypatch.setattr(pages.work_routes, "_presentations", lambda jobs: {})
    monkeypatch.setattr(pages.operation_store, "list_operations_pii_minimized", lambda: [])
    monkeypatch.setattr(pages.receipt_store, "list_receipts", lambda: [])
    monkeypatch.setattr(pages, "list_ai_ta_files", lambda: [])
    monkeypatch.setattr(pages, "list_quiz_files", lambda: [])
    monkeypatch.setattr(pages, "list_assignment_files", lambda: [])
    monkeypatch.setattr(pages, "list_page_files", lambda: [])
    monkeypatch.setattr(powergrader, "list_rubric_files", lambda: [])
    monkeypatch.setattr(powergrader, "_load_session", lambda session_id: {
        "session_id": session_id,
        "assignment_name": "Fictional Reflection",
        "course_id": "course-1",
        "mode": "fast",
        "students": [],
    })
    monkeypatch.setattr(powergrader.source_materials, "ensure_source_folder", lambda: "")
    monkeypatch.setattr(powergrader.source_materials, "list_source_files", lambda: [])
    monkeypatch.setattr(powergrader.workspace, "workspace_root", lambda: None)
    monkeypatch.setattr(powergrader.workspace, "folder", lambda name: "")


def test_registry_is_the_full_program_route_map():
    assert len(EXPECTED_PRESENTATION) == 13
    assert set(MIGRATED_ROUTES) == {
        "/", "/course-expert", "/powergrader", "/powergrader/session/{session_id}",
    }


def test_migrated_templates_use_only_the_workspace_layout_and_no_inline_styles():
    for _, (template, layout, _, _, migrated) in EXPECTED_PRESENTATION.items():
        if not migrated:
            continue
        text = (TEMPLATES / template).read_text(encoding="utf-8")
        assert f'{{% extends "layouts/{layout}.html" %}}' in text
        assert "stylesheet_bundle" not in text
        assert 'style="' not in text

    for layout in ("workspace.html", "document.html"):
        assert '{% extends "base.html" %}' in (TEMPLATES / "layouts" / layout).read_text(encoding="utf-8")


def test_migrated_feature_css_consumes_shared_visual_tokens():
    for relative in FEATURE_CSS:
        assert not VISUAL_LITERAL_RE.search(_source(relative)), relative


def test_shared_component_classes_are_not_javascript_hooks():
    for path in (ROOT / "api" / "webui" / "static").rglob("*.js"):
        text = path.read_text(encoding="utf-8")
        for selector in FORBIDDEN_JS_SELECTORS:
            assert not re.search(
                rf"(?:querySelector|querySelectorAll|getElementsByClassName)\([^\n]*{re.escape(selector)}",
                text,
            ), f"{path.relative_to(ROOT)} uses {selector} as a JavaScript hook"


def test_migrated_routes_render_the_expected_isolated_shell(monkeypatch):
    _configure_fictional(monkeypatch)
    routes = {
        "/": "/",
        "/course-expert": "/course-expert",
        "/powergrader": "/powergrader",
        "/powergrader/session/{session_id}": "/powergrader/session/synthetic-session",
    }
    client = _client()
    bundle = (
        "/static/ui/tokens.css", "/static/ui/foundation.css",
        "/static/ui/components.css", "/static/ui/layouts.css",
    )
    for key, url in routes.items():
        _, layout, variant, rails, _ = EXPECTED_PRESENTATION[key]
        response = client.get(url)
        assert response.status_code == 200, url
        text = response.text
        assert f'data-ce-layout="{layout}"' in text
        assert f'ce-{layout}--{variant}' in text
        assert text.count("<header") == 1
        assert text.count("<main") == 1
        assert len(re.findall(r'class="[^"]*\bce-rail\b', text)) == rails
        assert "/static/style.css" not in text
        assert "/static/workbench.css" not in text
        for href in bundle:
            assert href in text
        ids = re.findall(r'\bid="([^"]+)"', text)
        assert len(ids) == len(set(ids)), url


def test_student_reports_redirect_is_preserved(monkeypatch):
    _configure_fictional(monkeypatch)
    response = _client().get("/course-expert?tab=students", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/students/reports"
