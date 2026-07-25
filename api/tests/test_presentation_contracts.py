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
    "/powergrader": ("powergrader_setup.html", "workspace", "left-main", 1, True),
    "/powergrader/session/{session_id}": ("powergrader_queue.html", "workspace", "full", 0, True),
    "/gradebook": ("gradebook.html", "workspace", "left-main", 1, True),
    "/roster": ("roster.html", "workspace", "left-main", 1, True),
    "/settings": ("settings.html", "workspace", "left-main", 1, True),
    # Automations sits on the workspace layout so its title shares a left edge
    # with the other primary-nav pages instead of jumping inward.
    "/routines": ("routines.html", "workspace", "full", 0, True),
    "/course": ("course.html", "document", "wide", 0, True),
    "/about": ("about.html", "document", "wide", 0, True),
    "/ai-expert": ("ai_expert.html", "document", "standard", 0, True),
    "/welcome": ("welcome.html", "wizard", "", 0, True),
}

MIGRATED_ROUTES = {
    route: row for route, row in EXPECTED_PRESENTATION.items() if row[4]
}
FEATURE_CSS = (
    "api/webui/static/pages/dashboard.css",
    "api/webui/static/pages/course_expert.css",
    "api/webui/static/powergrader_setup.css",
    "api/webui/static/powergrader_queue.css",
    "api/webui/static/pages/gradebook.css",
    "api/webui/static/roster_workbench.css",
    "api/webui/static/pages/settings.css",
    "api/webui/static/pages/routines.css",
    "api/webui/static/pages/student_reports.css",
    "api/webui/static/pages/course.css",
    "api/webui/static/pages/about.css",
    "api/webui/static/pages/ai_expert.css",
    "api/webui/static/pages/welcome.css",
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
    monkeypatch.setattr(pages.config, "get_workspace_path", lambda: "")
    monkeypatch.setattr(pages.config, "active_courses", lambda: courses)
    monkeypatch.setattr(pages.config, "saved_courses", lambda: courses)
    monkeypatch.setattr(pages.config, "has_openrouter_key", lambda: False)
    monkeypatch.setattr(pages.config, "get_openrouter_model", lambda: "model/fictional")
    monkeypatch.setattr(pages.config, "openrouter_model_presets", lambda: [])
    monkeypatch.setattr(pages.config, "get_download_root", lambda: "")
    monkeypatch.setattr(pages.config, "get_calendars", lambda: {})
    monkeypatch.setattr(pages.config, "get_tier_tags", lambda: {
        "Support": "", "Core": "", "Accelerate": "", "Extend": "",
    })
    monkeypatch.setattr(pages.workspace, "workspace_root", lambda: None)
    monkeypatch.setattr(pages.workspace, "onedrive_root", lambda: "Fictional")
    monkeypatch.setattr(pages.workspace, "folder", lambda name: "")
    monkeypatch.setattr(pages.workspace, "library_folder", lambda name: "")
    monkeypatch.setattr(pages.workspace, "to_review_root", lambda: "")
    monkeypatch.setattr(pages.workspace, "printables_root", lambda: "")
    monkeypatch.setattr(pages.workspace, "canvas_uploads_root", lambda: "")
    monkeypatch.setattr(pages.workspace, "student_work_root", lambda: "")
    monkeypatch.setattr(pages.workspace, "for_ai_root", lambda: "")
    monkeypatch.setattr(pages.workspace, "system_root", lambda: "")
    monkeypatch.setattr(pages.work_routes, "_section_jobs", lambda section: [])
    monkeypatch.setattr(pages.work_routes, "_presentations", lambda jobs, finding_names=None: {})
    monkeypatch.setattr(pages.operation_store, "list_operations_pii_minimized", lambda: [])
    monkeypatch.setattr(pages.receipt_store, "list_receipts", lambda: [])
    monkeypatch.setattr(pages, "list_ai_ta_files", lambda: [])
    monkeypatch.setattr(pages, "list_quiz_files", lambda: [])
    monkeypatch.setattr(pages, "list_assignment_files", lambda: [])
    monkeypatch.setattr(pages, "list_page_files", lambda: [])
    monkeypatch.setattr(pages, "list_calendar_files", lambda: [])
    monkeypatch.setattr(pages, "_routines_template_context", lambda: {
        "custom_dir": "Fictional/custom_routines",
        "authoring_path": "Fictional/custom_routines/AUTHORING.md",
        "custom_active": [],
        "custom_templates": [],
        "active_count": 1,
    })
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
    assert len(EXPECTED_PRESENTATION) == 12
    assert set(MIGRATED_ROUTES) == set(EXPECTED_PRESENTATION)


def test_all_live_templates_use_layouts_and_no_inline_styles():
    for _, (template, layout, _, _, migrated) in EXPECTED_PRESENTATION.items():
        assert migrated
        text = (TEMPLATES / template).read_text(encoding="utf-8")
        assert f'{{% extends "layouts/{layout}.html" %}}' in text
        assert "stylesheet_bundle" not in text
        assert 'style="' not in text
        if template == "gradebook.html" or template == "routines.html":
            assert 'style="' not in (TEMPLATES / "_routines_panel.html").read_text(encoding="utf-8")

    for layout in ("workspace.html", "document.html", "wizard.html"):
        assert '{% extends "base.html" %}' in (TEMPLATES / "layouts" / layout).read_text(encoding="utf-8")

    for template in TEMPLATES.rglob("*.html"):
        assert 'style="' not in template.read_text(encoding="utf-8"), template.relative_to(ROOT)


def test_migrated_feature_css_consumes_shared_visual_tokens():
    for relative in FEATURE_CSS:
        assert not VISUAL_LITERAL_RE.search(_source(relative)), relative


def test_legacy_presentation_layer_is_gone():
    for relative in (
        "api/webui/static/style.css",
        "api/webui/static/workbench.css",
        "api/webui/templates/workbench_base.html",
        "api/webui/templates/_workbench_header.html",
        "api/webui/templates/name_manager.html",
        "api/webui/templates/_course_picker.html",
    ):
        assert not (ROOT / relative).exists(), relative
    for template in TEMPLATES.rglob("*.html"):
        text = template.read_text(encoding="utf-8")
        assert "/static/style.css" not in text, template.relative_to(ROOT)
        assert "/static/workbench.css" not in text, template.relative_to(ROOT)


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
        "/gradebook": "/gradebook",
        "/roster": "/roster",
        "/settings": "/settings",
        "/routines": "/routines",
        "/course": "/course",
        "/about": "/about",
        "/ai-expert": "/ai-expert",
        "/welcome": "/welcome",
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
        if variant:
            assert f'ce-{layout}--{variant}' in text
        else:
            assert f'ce-{layout}' in text
        assert text.count("<header") == (0 if layout == "wizard" else 1)
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
    for url in ("/course-expert?tab=students", "/students/reports"):
        response = _client().get(url, follow_redirects=False)
        assert response.status_code == 307, url
        assert response.headers["location"] == "/roster?focus=reports", url


def test_create_first_session_notice_is_present_only_without_current_courses(monkeypatch):
    _configure_fictional(monkeypatch)
    monkeypatch.setattr(pages.config, "active_courses", lambda: [])
    empty_render = _client().get("/course-expert").text
    assert empty_render.count('data-ce-hook="first-session-course-notice"') == 1
    assert '/settings#add-courses-card' in empty_render
    assert empty_render.index('data-ce-hook="first-session-course-notice"') < empty_render.index('class="ce-panel ce-forge-start"')
    assert "Start in your assistant" in empty_render
    assert 'data-ce-hook="course-tab"' in empty_render

    _configure_fictional(monkeypatch)
    configured_render = _client().get("/course-expert").text
    assert 'data-ce-hook="first-session-course-notice"' not in configured_render


def test_create_title_matches_its_navigation_and_page_title(monkeypatch):
    _configure_fictional(monkeypatch)
    text = _client().get("/course-expert").text
    assert "<title>Create — Canvas Expert</title>" in text
    assert ">Create<" in text
