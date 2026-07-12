"""Source-contract tests for WebUI templates and client JS.

These guard against specific P1 regression modes. They read source files
directly — no live Canvas, no server, no student data.
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _slurp(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_operation_gateway_aliases_and_no_direct_legacy_calls():
    core = _slurp("api/webui/static/push/core.js")
    for alias, kind in {
        "qf": "content.quiz",
        "quick": "content.quick_assignment",
        "af": "content.assignment",
        "pf": "content.page",
        "rf": "content.rubric",
    }.items():
        assert f'{alias}: "{kind}"' in core
    for rel in (
        "api/webui/static/push/assignment.js",
        "api/webui/static/push/page.js",
        "api/webui/static/push/rubric.js",
        "api/webui/static/course_expert/quick_assignment.js",
    ):
        assert "/api/content/push" not in _slurp(rel)
    assert '{ payload: payload, targets: targets }' in core


def test_quiz_push_uses_typed_operation_payloads_not_streaming_writes():
    quiz = _slurp("api/webui/static/push/quiz.js")
    assert 'push.pushContent(' in quiz
    assert '"qf"' in quiz
    assert '{ mode: "whole", path: path, settings: settingsObj }' in quiz
    assert '{ mode: "differentiated", variants: variants, settings: settingsObj }' in quiz
    for legacy_route in (
        "/api/push/stream",
        "/api/push-multi-whole/stream",
        "/api/push-variants/stream",
        "/api/push-multi/stream",
    ):
        assert legacy_route not in quiz
    assert "push.streamSSE(" not in quiz
    assert "push.canvasWriteReview(" not in quiz
    assert "studentIds:" not in quiz


def test_operation_summary_polling_uses_ordinal_labels_only():
    core = _slurp("api/webui/static/push/core.js")
    assert '"/api/operations/" + encodeURIComponent(operationId) + "/status"' in core
    assert "Target ' + (targetIndex + 1)" in core
    assert "Step ' + (stepIndex + 1)" in core
    assert "target.target_key" not in core
    assert "step.step_key" not in core
    assert 'window.addEventListener("pagehide"' in core


def test_shared_csrf_meta_and_push_script_order():
    base = _slurp("api/webui/templates/base.html")
    workbench = _slurp("api/webui/templates/workbench_base.html")
    assert base.count('name="canvasexpert-csrf-token"') == 1
    assert 'content="{{ csrf_token }}"' in base
    assert 'canvasexpert-csrf-token' not in workbench
    common = _slurp("api/webui/templates/_push_common_scripts.html")
    assert common.index("/static/push/core.js") < common.index("/static/push/course_picker.js")
    course_expert_html = _slurp("api/webui/templates/course_expert.html")
    assert course_expert_html.index('_push_common_scripts.html') < course_expert_html.index("/static/push/quiz.js")


def test_page_prepare_uses_shared_operation_helper():
    page = _slurp("api/webui/static/push/page.js")
    assert 'push.prepareOnly("content.page"' in page
    assert "function postJson" not in page
    assert "function renderOperationsList" not in page


def test_operation_alias_runtime_cancellation_never_applies():
    core_path = ROOT / "api/webui/static/push/core.js"
    script = r'''
import fs from "node:fs";
import vm from "node:vm";
const calls = [];
global.window = {
  CE_WRITE_REVIEW: { confirm: async () => false },
  CE_PUSH: { targetCourses: () => [{id: "101", name: "Fictional Course"}] }
};
global.document = {
  querySelector: () => ({getAttribute: () => "csrf-test"}),
  querySelectorAll: () => [],
  getElementById: () => null,
  addEventListener: () => {}
};
global.alert = () => {};
global.fetch = async (url, options) => {
  calls.push({url, body: options && options.body});
  if (url.includes("/prepare")) return {ok: true, status: 200, json: async () => ({ok: true, operation_id: "op-test"})};
  if (url.includes("/review")) return {ok: true, status: 200, json: async () => ({ok: true, batch_id: "batch-test", review_digest: "digest", frozen_reviews: [{course_name: "Fictional Course", assignment_name: "Test"}]})};
  throw new Error("unexpected fetch " + url);
};
vm.runInThisContext(fs.readFileSync(process.argv[1], "utf8"));
const log = {hidden: true, textContent: "", scrollTop: 0, scrollHeight: 0};
for (const alias of ["quick", "af", "pf", "rf"]) {
  await window.CE_PUSH.pushContent(alias, {name: "Test"}, log, null, {disabled: false}, "Review Test");
}
if (calls.some(c => c.url === "/api/content/push" || c.url.includes("/apply"))) process.exit(2);
if (calls.filter(c => c.url.includes("/prepare")).length !== 4) process.exit(3);
if (calls.filter(c => c.url.includes("/prepare")).some(c => JSON.parse(c.body).targets[0].course_id !== "101")) process.exit(4);
'''
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script, str(core_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


# ── feedback_expert.html ──────────────────────────────────────────────

def test_persona_card_closed_before_push_section():
    """The </section> closing #persona-card must appear before id="push-section"."""
    html = _slurp("api/webui/templates/feedback_expert.html")
    # Find position of first </section> after id="persona-card"
    persona_start = html.index('id="persona-card"')
    first_close_after_persona = html.index("</section>", persona_start)
    push_start = html.index('id="push-section"')
    assert first_close_after_persona < push_start, (
        "Expected </section> closing #persona-card before #push-section. "
        "DOM nesting regression: push-section may be nested inside persona-card."
    )


# ── powergrader_setup.html ────────────────────────────────────────────

def test_powergrader_config_has_workspace():
    """POWERGRADER_SETUP_CONFIG must contain hasWorkspace from has_workspace."""
    html = _slurp("api/webui/templates/powergrader_setup.html")
    assert 'hasWorkspace: {{ has_workspace | tojson }}' in html, (
        "POWERGRADER_SETUP_CONFIG missing hasWorkspace key sourced from "
        "has_workspace template variable."
    )


# ── setup_core.js ─────────────────────────────────────────────────────

def test_sync_start_enabled_uses_workspace_flag():
    """syncStartEnabled must gate on setupConfig.hasWorkspace."""
    js = _slurp("api/webui/static/powergrader/setup_core.js")
    assert "setupConfig.hasWorkspace" in js, (
        "syncStartEnabled does not reference setupConfig.hasWorkspace — "
        "workspace prerequisite may not be enforced."
    )
    assert "startBtn.disabled = !(setupConfig.hasWorkspace" in js, (
        "syncStartEnabled enable condition must include hasWorkspace as "
        "the first conjunct."
    )


# ── base.html ─────────────────────────────────────────────────────────

def test_write_review_loaded_before_page_scripts():
    """base.html must load write_review.js synchronously in <head> before content."""
    html = _slurp("api/webui/templates/base.html")
    wr_idx = html.index("/static/write_review.js")
    content_idx = html.index("{% block content %}")
    head_close_idx = html.index("</head>")

    # Must occur exactly once
    assert html.count("/static/write_review.js") == 1, (
        "write_review.js must appear exactly once in base.html"
    )
    # Must be before {% block content %}
    assert wr_idx < content_idx, (
        "write_review.js must load before {% block content %}"
    )
    # Must be before </head>
    assert wr_idx < head_close_idx, (
        "write_review.js must be inside <head>"
    )
    # The containing tag must not have defer or async
    tag_start = html.rindex("<script", 0, wr_idx)
    tag_end = html.index(">", tag_start)
    tag = html[tag_start:tag_end]
    assert "defer" not in tag, "write_review.js script tag must not use defer"
    assert "async" not in tag, "write_review.js script tag must not use async"


# ── scoped Workbench visual foundation (slice 1) ─────────────────────

def test_base_loads_workbench_css_once_after_legacy_css():
    """The inert foundation stylesheet must load once between style and scripts."""
    html = _slurp("api/webui/templates/base.html")
    workbench = html.index('/static/workbench.css?v={{ asset_v }}')
    legacy = html.index('/static/style.css?v={{ asset_v }}')
    review = html.index('/static/write_review.js?v={{ asset_v }}')
    assert html.count('/static/workbench.css?v={{ asset_v }}') == 1
    assert legacy < workbench < review, (
        "workbench.css must load after style.css and before write_review.js"
    )


def test_base_exposes_slice_one_extension_blocks_once_in_order():
    """Base extension points must remain stable for later shell migrations."""
    html = _slurp("api/webui/templates/base.html")
    blocks = [
        "{% block head_extra %}",
        "{% block app_header %}",
        "{% block status_strip %}",
        "{% block scripts_extra %}",
    ]
    for block in blocks:
        assert html.count(block) == 1, f"Expected one {block} block"
    assert html.index(blocks[0]) < html.index("</head>")
    assert html.index(blocks[1]) < html.index(blocks[2]) < html.index("<main ")
    assert html.index(blocks[3]) < html.index("</body>")


def test_base_loads_app_context_after_write_review_before_content():
    """Shared context must be ready before child-page scripts execute."""
    html = _slurp("api/webui/templates/base.html")
    context = html.index('/static/app_context.js?v={{ asset_v }}')
    review = html.index('/static/write_review.js?v={{ asset_v }}')
    content = html.index('{% block content %}')
    assert html.count('/static/app_context.js?v={{ asset_v }}') == 1
    assert review < context < content


def test_workbench_css_is_namespaced_and_has_required_tokens():
    """Foundation CSS must not leak generic page rules into legacy routes."""
    css = _slurp("api/webui/static/workbench.css")
    assert ".ce-desk-shell" in css
    assert ".ce-workbench-shell" in css
    assert ".ce-instrument-shell" in css
    for forbidden in [".card", ".page", "button", "input", "select"]:
        assert re.search(rf"(?m)^\s*{re.escape(forbidden)}(?:\s|,|\{{)", css) is None, (
            f"workbench.css must not define generic selector {forbidden!r}"
        )
    for token in ["--ce-paper", "--ce-graphite", "--ce-canvas", "--ce-privacy",
                  "--ce-attention", "--ce-prepared", "--ce-create", "--ce-grade",
                  "--ce-ledger-rule", "--ce-grid-line", "--ce-focus"]:
        assert token in css, f"Missing scoped foundation token {token}"


def test_course_picker_uses_shared_context_without_dual_writes():
    """CoursePicker must publish to CE_CONTEXT and stop writing its legacy key."""
    js = _slurp("api/webui/static/push/course_picker.js")
    assert "window.CE_CONTEXT" in js
    assert "context.setFocus" in js
    assert "context.setTargets" in js
    assert "authoritative: true" in js
    assert "canvasExpert.push.coursePicker.v1" not in js


def test_workbench_header_owns_single_readiness_root_and_script():
    """Workbench header owns the only readiness markup; its base owns one script."""
    base = _slurp("api/webui/templates/base.html")
    workbench = _slurp("api/webui/templates/workbench_base.html")
    header = _slurp("api/webui/templates/_workbench_header.html")
    readiness = _slurp("api/webui/templates/_readiness_strip.html")
    assert "_readiness_strip.html" not in base
    assert "_readiness_strip.html" not in workbench
    assert header.count('{% include "_readiness_strip.html" %}') == 1
    assert header.index('</nav>') < header.index('_readiness_strip.html') < header.index('class="topbar-right"')
    assert readiness.count('id="ce-readiness-strip"') == 1
    assert workbench.count('/static/readiness.js?v={{ asset_v }}') == 1
    assert '/static/readiness.js' not in base


def test_workbench_readiness_preserves_behavior_and_accessibility_hooks():
    """Moving readiness must not change its JS or accessible DOM contract."""
    readiness = _slurp("api/webui/templates/_readiness_strip.html")
    assert 'aria-live="polite"' in readiness
    assert 'data-status="unknown"' in readiness
    for component in ("canvas", "openrouter", "privacy"):
        assert readiness.count(f'data-readiness-component="{component}"') == 1
        assert readiness.count(f'data-readiness-dot="{component}"') == 1
        assert readiness.count(f'data-readiness-value="{component}"') == 1
    for hook in ("data-readiness-refresh", "data-readiness-details", "data-readiness-detail"):
        assert len(re.findall(rf"\s{hook}(?:\s|>)", readiness)) == 1
    assert "Refresh" in readiness
    assert "Readiness details" in readiness


def test_workbench_header_stays_scoped_and_preserves_controls():
    """The shared partial is Workbench-only and keeps its link/theme contracts."""
    base = _slurp("api/webui/templates/base.html")
    workbench = _slurp("api/webui/templates/workbench_base.html")
    header = _slurp("api/webui/templates/_workbench_header.html")
    assert "_workbench_header.html" not in base
    assert '{% include "_workbench_header.html" %}' in workbench
    assert 'class="topbar ce-workbench-header"' in header
    for href, label in [
        ('/', 'Desk'),
        ('/course-expert', 'Create'),
        ('/powergrader', 'Grade'),
        ('/roster', 'Students'),
        ('/routines', 'Automations'),
        ('/settings', 'Settings'),
    ]:
        assert f'href="{href}"' in header
        assert f'>{label}</a>' in header
    assert 'class="theme-toggle"' in header
    assert 'id="theme-toggle"' in header
    assert 'aria-label="Toggle theme"' in header


def test_workbench_header_has_server_derived_active_states():
    """Every destination gets one truthful server-derived aria-current state."""
    header = _slurp("api/webui/templates/_workbench_header.html")
    assert "request.url.path == '/'" in header
    for section in ["create", "grade", "manage", "automate", "settings"]:
        assert f"workbench_section == '{section}'" in header
    assert header.count("ce-workbench-nav-link--active") == 6
    assert header.count('aria-current="page"') == 6


def test_workbench_header_css_owns_scoped_narrow_composition():
    """Workbench header styling remains scoped and owns its CSS-only narrow row."""
    css = _slurp("api/webui/static/workbench.css")
    assert ".ce-workbench-header.topbar" in css
    assert 'html[data-theme="dark"] .ce-workbench-header.topbar' in css
    intermediate = css[css.index("@media (max-width: 1180px)"):css.index("@media (max-width: 760px)")]
    for selector, column, row in (
        (r"\.ce-workbench-header\.topbar \.brand", "1", "1"),
        (r"\.ce-workbench-header\.topbar nav", "2", "1"),
        (r"\.ce-workbench-header\.topbar \.topbar-right", "3", "1"),
        (r"\.ce-workbench-header\.topbar \.ce-status-strip", "1 / -1", "2"),
    ):
        assert re.search(
            rf"{selector}\s*\{{[^}}]*grid-column: {re.escape(column)};[^}}]*grid-row: {row};",
            intermediate,
            re.DOTALL,
        )
    narrow = css[css.index("@media (max-width: 760px)"):]
    for selector, column, row in (
        (r"\.ce-workbench-header\.topbar \.brand", "1", "1"),
        (r"\.ce-workbench-header\.topbar \.topbar-right", "2", "1"),
        (r"\.ce-workbench-header\.topbar nav", "1 / -1", "2"),
        (r"\.ce-workbench-header\.topbar \.ce-status-strip", "1 / -1", "3"),
    ):
        assert re.search(
            rf"{selector}\s*\{{[^}}]*grid-column: {re.escape(column)};[^}}]*grid-row: {row};",
            narrow,
            re.DOTALL,
        )
    assert "overflow-x: auto" in narrow
    assert ".ce-workbench-header .ce-status-strip .ce-readiness-details[open] [data-readiness-detail]" in css
    assert "max-width: min(420px, calc(100vw - 32px))" in css
    assert re.search(r"(?m)^\.topbar\s*\{", css) is None


def test_desk_starts_with_compact_controls_without_visible_hero():
    """Desk orientation stays in the active header while its controls remain intact."""
    html = _slurp("api/webui/templates/dashboard.html")
    assert 'id="desk-root" class="ce-desk-shell" aria-label="Desk"' in html
    assert "ce-desk-intro" not in html
    assert "desk-title" not in html
    assert re.search(r"<h1(?:\s|>)", html) is None
    toolbar_start = html.index('class="ce-desk-toolbar"')
    tools_start = html.index('class="ce-desk-grid"')
    toolbar = html[toolbar_start:tools_start]
    assert 'aria-label="Desk controls"' in toolbar
    for control_id in ("desk-course-field", "desk-scope-note", "desk-local-status", "desk-scan"):
        assert toolbar.count(f'id="{control_id}"') == 1
    assert toolbar.index('id="desk-course-field"') < toolbar.index('id="desk-local-status"') < toolbar.index('id="desk-scan"')
    assert '<option value="">Keep saved context</option>' in toolbar
    assert '<option value="__all__">All active courses</option>' in toolbar


def test_desk_intro_css_is_removed_and_toolbar_owns_compact_layout():
    css = _slurp("api/webui/static/workbench.css")
    for removed in (".ce-desk-intro", ".ce-desk-kicker", ".ce-desk-lede"):
        assert removed not in css
    assert "grid-template-columns: minmax(260px, 360px) minmax(0, 1fr) auto" in css
    assert ".ce-desk-local-state" in css


def test_powergrader_review_apply_contract():
    """Manual pushes must review first and send the frozen token to apply."""
    js = _slurp("api/webui/static/powergrader/queue_review.js")
    assert "/push-review" in js
    assert "review_token" in js
    assert "CE_WRITE_REVIEW.confirm" in js
    assert "Apply approved grades and feedback" in js
    assert "status !== 'pushed' && result.status !== 'already_applied'" in js


def test_powergrader_import_uses_shared_session_id():
    """Packet links must use the queue namespace session id, not an IIFE-local name."""
    js = _slurp("api/webui/static/powergrader/queue_import.js")
    assert "queue.getSessionId" in js
    assert "SESSION_ID" not in js


# ── No legacy canvasWriteReview function definitions ──────────────────

def test_no_local_canvas_write_review_function():
    """No file in api/webui/static may define function canvasWriteReview."""
    import glob
    found = []
    for f in glob.glob(str(ROOT / "api/webui/static/**/*.js"), recursive=True):
        with open(f, encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                if "function canvasWriteReview" in line:
                    found.append(f"{f}:{i}: {line.strip()}")
    assert not found, (
        "Legacy canvasWriteReview function definitions remain:\n" +
        "\n".join(found)
    )


# ── Action-scope elements ─────────────────────────────────────────────

def test_gradebook_has_action_scope():
    """gradebook.html must contain ce-action-scope element with aria-live."""
    html = _slurp("api/webui/templates/gradebook.html")
    assert 'class="ce-action-scope"' in html, (
        "gradebook.html missing ce-action-scope element"
    )
    assert 'aria-live="polite"' in html, (
        "gradebook.html action scope missing aria-live attribute"
    )
    assert "No course selected. Gradebook changes are unavailable." in html, (
        "gradebook.html missing default no-course readiness text"
    )


def test_feedback_push_has_action_scope():
    """feedback_expert.html Push section must contain ce-action-scope."""
    html = _slurp("api/webui/templates/feedback_expert.html")
    assert 'id="fb-action-scope"' in html, (
        "feedback_expert.html missing #fb-action-scope in Push section"
    )


# ── Navigation taxonomy ───────────────────────────────────────────────

def test_nav_taxonomy_labels_present():
    """base.html must contain all six new taxonomy labels."""
    html = _slurp("api/webui/templates/base.html")
    labels = ["Create", "Grade", "Manage", "Automate", "Settings", "Help &amp; tools"]
    for label in labels:
        assert label in html, (
            f"Navigation label '{label}' not found in base.html"
        )


def test_legacy_nav_labels_absent():
    """base.html must not contain legacy top-level navigation labels."""
    html = _slurp("api/webui/templates/base.html")
    legacy = ["Work ▾", "Gradebooks ▾", "Extras ▾"]
    for label in legacy:
        assert label not in html, (
            f"Legacy navigation label '{label}' still present in base.html"
        )


def test_dashboard_has_desk_start_surface():
    """The Desk must expose its Tools section and course context."""
    html = _slurp("api/webui/templates/dashboard.html")
    assert 'id="desk-course-field"' in html
    for heading in ["Tools", "In progress", "Needs review", "Prepared", "Receipts"]:
        assert f">{heading}<" in html


def test_desk_contract_keeps_workbench_boundaries():
    """Desk opts into the Workbench shell without leaking legacy concerns."""
    html = _slurp("api/webui/templates/dashboard.html")
    js = _slurp("api/webui/static/desk.js")
    workbench = _slurp("api/webui/templates/workbench_base.html")
    assert "Teacher Jobs" not in html
    assert "/api/operations" not in html + js
    assert "/api/work/scan" in js
    assert "/api/work?section=all" in js
    assert "/api/receipts" in js
    assert "No prepared operations." in html
    assert 'name="canvasexpert-csrf-token"' in _slurp("api/webui/templates/base.html")
    assert 'name="canvasexpert-csrf-token"' not in workbench
    assert "/static/workbench.css" not in workbench
    assert js.count("X-CanvasExpert-CSRF") == 1


def test_workbench_instrument_language_and_drafting_grid_contract():
    """Named working panes use the grid and operational copy survives rerenders."""
    templates = {
        "course": _slurp("api/webui/templates/course_expert.html"),
        "gradebook": _slurp("api/webui/templates/gradebook.html"),
        "roster": _slurp("api/webui/templates/roster.html"),
        "powergrader": _slurp("api/webui/templates/powergrader_setup.html"),
    }
    assert 'class="ce-course-expert-center ce-drafting-grid"' in templates["course"]
    assert 'class="gb-content expert-main ce-drafting-grid"' in templates["gradebook"]
    assert 'class="roster-workbench-main ce-drafting-grid"' in templates["roster"]
    assert 'class="pg-workbench-content ce-drafting-grid"' in templates["powergrader"]

    dashboard = _slurp("api/webui/templates/dashboard.html")
    desk_js = _slurp("api/webui/static/desk.js")
    for text in [
        ">Course context<", "Saved targets are unchanged.",
        'id="desk-local-status">Local state.</span>', ">Tools<", ">In progress<", ">Needs review<",
        ">Prepared<", ">Receipts<", "No open work.",
        "No items need review.", "No prepared operations.", "No receipts.",
    ]:
        assert text in dashboard
    for text in ["No open work.", "No items need review.", "No receipts.", "Local state updated."]:
        assert text in desk_js
    for old_text in ["The work in front of you.", "Resume local work.", "Needs a decision."]:
        assert old_text not in dashboard
    assert "Using local projections." not in dashboard
    assert "<strong>Local state.</strong>" not in dashboard

    course_js = _slurp("api/webui/static/course_expert/work_rail.js")
    for heading in ["Tools", "In progress", "Review"]:
        assert f">{heading}<" in templates["course"]
    assert templates["course"].count("None.") == 2
    assert "None." in course_js

    assert '<h1 id="roster-title">Roster</h1>' in templates["roster"]
    assert "Student settings for CanvasExpert" not in templates["roster"]
    assert "roster-v2-kicker" not in templates["roster"]

    power_js = _slurp("api/webui/static/powergrader/setup_sessions.js")
    for heading in ["Sessions", "Ready to post", "In progress"]:
        assert f">{heading}<" in templates["powergrader"]
    assert "Open an existing session instead of starting a duplicate." in templates["powergrader"]
    assert "Grade locally, prepare a pseudonymized packet for your AI chat, or draft-score with OpenRouter." in templates["powergrader"]
    assert "<strong>Grade one assignment.</strong>" not in templates["powergrader"]
    assert "pg-lane-description" not in templates["powergrader"]
    assert "return 'None.';" in power_js

    css = _slurp("api/webui/static/workbench.css")
    grid_rules = re.findall(
        r"\.ce-workbench-page\s+\.ce-drafting-grid\s*\{([^}]*)\}",
        css,
        re.DOTALL,
    )
    assert any("background-size: 24px 24px" in rule for rule in grid_rules)
    assert any("padding: 12px" in rule for rule in grid_rules)
    assert 'html[data-theme="dark"] .ce-drafting-grid' in css


def test_desk_start_links_preserve_existing_routes():
    """Start cards now link into Course Expert canonical tabs."""
    html = _slurp("api/webui/templates/dashboard.html")
    expected = [
        "/course-expert?tab=assignment", "/course-expert?tab=quiz", "/course-expert?tab=quick", "/course-expert?tab=page",
        "/course-expert?tab=rubric", "/powergrader", "/gradebook", "/roster",
        "/course-expert?tab=students", "/course-expert?tab=download", "/routines",
    ]
    for route in expected:
        assert f'href="{route}"' in html


def test_route_nav_sections_updated():
    """pages.py must use new nav_section values."""
    src = _slurp("api/webui/routes/pages.py")
    assert '"nav_section":   "create"' in src, (
        "pages.py missing nav_section=create for Work routes"
    )
    assert '"nav_section":   "grade"' in src, (
        "pages.py missing nav_section=grade for Gradebook routes"
    )
    assert '"nav_section":   "manage"' in src, (
        "pages.py missing nav_section=manage for Roster/Course routes"
    )
    assert '"nav_section":      "automate"' in src, (
        "pages.py missing nav_section=automate for Routines route"
    )


# ── CourseExpert workbench contract ───────────────────────────────────

def test_course_expert_extends_workbench_base():
    """course_expert.html must extend workbench_base.html."""
    html = _slurp("api/webui/templates/course_expert.html")
    assert '{% extends "workbench_base.html" %}' in html


def test_course_expert_keeps_ce_screen_class():
    """course_expert.html keeps ce-screen class for CSS scoping."""
    html = _slurp("api/webui/templates/course_expert.html")
    assert 'ce-screen' in html


def test_course_expert_has_work_rail():
    """course_expert.html must contain the work rail with Start sections."""
    html = _slurp("api/webui/templates/course_expert.html")
    assert 'class="ce-work-rail"' in html
    assert 'data-rail-tab="quiz"' in html
    assert 'data-rail-tab="assignment"' in html
    assert 'data-rail-tab="page"' in html
    assert 'data-rail-tab="rubric"' in html
    assert 'data-rail-tab="download"' in html
    assert 'data-rail-tab="students"' in html
    assert 'data-rail-tab="quick"' in html


def test_course_expert_grid_collapses_at_intermediate_width():
    """Course Expert must not squeeze its three workbench columns on tablets."""
    css = _slurp("api/webui/static/workbench.css")
    responsive = css[css.index("@media (max-width: 980px)"):]
    grid = re.search(
        r"\.ce-workbench-grid\.ce-course-expert-grid\s*\{([^}]*)\}",
        responsive,
        re.DOTALL,
    )
    assert grid and re.search(
        r"grid-template-columns:\s*minmax\(0,\s*1fr\)", grid.group(1)
    )
    assert ".ce-course-expert-grid > .ce-work-rail" in responsive
    assert ".ce-course-expert-grid .ce-course-expert-center" in responsive
    assert ".ce-course-expert-grid .ce-summary-panel" in responsive


def test_course_expert_preserves_all_critical_ids():
    """Every critical DOM ID from the legacy template must still exist."""
    html = _slurp("api/webui/templates/course_expert.html")
    critical_ids = [
        "ce-tab-button-quiz", "ce-tab-button-assignment", "ce-tab-button-page",
        "ce-tab-button-rubric", "ce-tab-button-download", "ce-tab-button-students",
        "ce-tab-button-quick", "ce-course-picker", "ce-picker-label", "target-count",
        "course-checklist", "ce-tab-quiz", "quiz-whole", "quizfile",
        "btn-validate", "btn-preview", "btn-push", "result", "push-banner",
        "quiz-diff", "groups-status", "variant-rows", "btn-add-variant",
        "btn-push-variants", "variants-result", "variants-banner",
        "due-at", "unlock-at", "lock-at",
        "assignment-group-select", "module-select", "new-module-name",
        "ce-tab-assignment", "assignment", "af-file", "af-rubric",
        "af-rubric-controls", "af-rubric-mode", "af-rubric-link",
        "btn-af-copy-prompt", "af-rubric-status", "btn-af-validate", "btn-af-push",
        "af-log", "af-banner",
        "ce-tab-page", "page", "pf-file", "btn-pf-validate", "btn-pf-prepare",
        "btn-pf-push",
        "pf-log", "pf-banner",
        "ce-tab-rubric", "rubric", "rf-file", "btn-rf-validate", "btn-rf-push",
        "rf-log", "rf-banner",
        "ce-tab-download", "download", "btn-load-assignments",
        "btn-download-selected", "dl-check-all", "dl-tbody", "dl-log", "dl-banner",
        "folder-path", "btn-open-folder", "btn-change-folder",
        "ce-tab-students", "sr-course", "sr-student", "sr-generate", "sr-log",
        "ce-tab-quick", "quick", "qa-name", "qa-points", "qa-subtype",
        "qa-aggroup", "qa-due", "qa-publish", "btn-qa-push", "qa-log", "qa-banner",
    ]
    for id_ in critical_ids:
        assert f'id="{id_}"' in html, f"Missing critical ID: {id_}"


def test_course_expert_preserves_script_order():
    """course_expert.html must include all push scripts in order."""
    html = _slurp("api/webui/templates/course_expert.html")
    expected_scripts = [
        "/static/push/quiz.js",
        "/static/push/page.js",
        "/static/push/rubric.js",
        "/static/push/assignment.js",
        "/static/push/download.js",
        "/static/course_expert/tabs.js",
        "/static/course_expert/student_reports.js",
        "/static/course_expert/portfolio.js",
        "/static/course_expert/quick_assignment.js",
        "/static/course_expert/instrument.js",
        "/static/course_expert/work_rail.js",
    ]
    for script in expected_scripts:
        assert script in html, f"Missing script include: {script}"


def test_course_expert_preserves_globals():
    """course_expert.html must set all required window globals."""
    html = _slurp("api/webui/templates/course_expert.html")
    required_globals = [
        "window.QF_FILES", "window.QF_QUIZ_FILES", "window.QF_ASSIGNMENT_FILES",
        "window.QF_PAGE_FILES", "window.QF_CANVAS_BASE", "window.QF_HISTORY",
        "window.QF_SAVED",
    ]
    for g in required_globals:
        assert g in html, f"Missing global: {g}"


def test_course_expert_has_summary_panel():
    """course_expert.html must have a summary panel with operations list container."""
    html = _slurp("api/webui/templates/course_expert.html")
    assert "Summary" in html
    assert 'id="ce-operations-list"' in html
    assert "Canvas unchanged." in html  # empty-state placeholder text


def test_work_rail_js_passes_syntax_check():
    """work_rail.js must pass Node syntax check."""
    import subprocess
    result = subprocess.run(
        ["node", "--check", "api/webui/static/course_expert/work_rail.js"],
        capture_output=True, text=True, shell=True,
    )
    assert result.returncode == 0, f"work_rail.js syntax error: {result.stderr}"


def test_instrument_js_passes_syntax_check():
    """instrument.js must pass Node syntax check."""
    import subprocess
    result = subprocess.run(
        ["node", "--check", "api/webui/static/course_expert/instrument.js"],
        capture_output=True, text=True, shell=True,
    )
    assert result.returncode == 0, f"instrument.js syntax error: {result.stderr}"


def test_tabs_js_exposes_instrument_api():
    """tabs.js must expose CE_COURSE_EXPERT instrument methods."""
    js = _slurp("api/webui/static/course_expert/tabs.js")
    assert "CE_COURSE_EXPERT.currentView" in js
    assert "CE_COURSE_EXPERT.setView" in js
    assert "CE_COURSE_EXPERT.toggleInstrument" in js
    assert "data-instrument-toggle" in js
    assert "popstate" in js
    assert 'params.get("view")' in js


def test_tabs_js_deep_link_tab_overrides_hash():
    """tabs.js must read ?tab= before #hash."""
    js = _slurp("api/webui/static/course_expert/tabs.js")
    assert "params.get(\"tab\") || location.hash" in js
    assert "view" in js


def test_standalone_push_templates_are_removed():
    """Standalone push templates are removed in the canonical Course Expert surface."""
    for tpl in ["push_quiz", "push_assignment", "push_page", "push_rubric", "push_quick"]:
        assert not (ROOT / f"api/webui/templates/{tpl}.html").exists(), (
            f"{tpl}.html should be removed when Course Expert is canonical"
        )


# ── AI safety: guided_run.js ─────────────────────────────────────────

def test_guided_run_uses_write_review_confirm():
    """guided_run.js must use CE_WRITE_REVIEW.confirm, not create backdrop directly."""
    js = _slurp("api/webui/static/feedback/guided_run.js")
    assert "CE_WRITE_REVIEW.confirm" in js, (
        "guided_run.js does not use CE_WRITE_REVIEW.confirm"
    )
    assert "ce-review-backdrop" not in js, (
        "guided_run.js still creates ce-review-backdrop directly"
    )


def test_guided_run_acknowledgement_text():
    """The acknowledgement text must be present in the template."""
    html = _slurp("api/webui/templates/feedback_expert.html")
    expected = "I understand that this sends the pseudonymized SAFE batch to OpenRouter. It may still contain identifying context."
    assert expected in html, (
        "feedback_expert.html missing or changed the required acknowledgement text"
    )


# ── AI safety: powergrader_setup ─────────────────────────────────────

def test_powergrader_safety_popout_has_id():
    """powergrader_setup.html must have pg-safety-popout id."""
    html = _slurp("api/webui/templates/powergrader_setup.html")
    assert 'id="pg-safety-popout"' in html, (
        "powergrader_setup.html missing id=pg-safety-popout on safety details"
    )


def test_powergrader_opens_safety_for_ai():
    """setup_core.js must programmatically open pg-safety-popout for AI routes."""
    js = _slurp("api/webui/static/powergrader/setup_core.js")
    assert "pg-safety-popout" in js, (
        "setup_core.js does not reference pg-safety-popout"
    )
    assert "safetyPopout.open = isAi" in js, (
        "setup_core.js does not open safety popout for AI routes"
    )


# ── PowerGrader visibility-state contract (slice 1) ──────────────────

def test_pg_assignment_tools_starts_hidden():
    """#pg-assignment-tools must have the boolean hidden attribute."""
    html = _slurp("api/webui/templates/powergrader_setup.html")
    assert 'id="pg-assignment-tools" hidden' in html or 'id="pg-assignment-tools"  hidden' in html, (
        "#pg-assignment-tools missing hidden attribute in template"
    )


def test_pg_ai_options_starts_hidden():
    """#pg-ai-options must use hidden, not inline display:none."""
    html = _slurp("api/webui/templates/powergrader_setup.html")
    assert 'id="pg-ai-options"' in html, (
        "#pg-ai-options must exist in template"
    )
    # Find the <section> containing id="pg-ai-options" and check it has hidden
    ai_start = html.index('id="pg-ai-options"')
    # Go back to the < to capture the full opening tag (may span multiple lines)
    line_start = html.rindex('<', 0, ai_start)
    ai_tag = html[line_start:ai_start + 200]
    assert 'hidden' in ai_tag, (
        "#pg-ai-options must use hidden attribute, not style='display:none'"
    )
    assert 'style="display:none"' not in html[html.index('id="pg-ai-options"'):html.index('id="pg-ai-options"') + 200], (
        "#pg-ai-options must not have inline display:none"
    )


def test_pg_ai_check_wrap_starts_hidden():
    """#pg-ai-check-wrap must use hidden, not inline display:none."""
    html = _slurp("api/webui/templates/powergrader_setup.html")
    assert 'id="pg-ai-check-wrap" hidden' in html, (
        "#pg-ai-check-wrap must use hidden attribute, not style='display:none'"
    )


def test_pg_api_only_containers_start_hidden():
    """Every .pg-api-only element must have the hidden attribute."""
    html = _slurp("api/webui/templates/powergrader_setup.html")
    import re
    api_only_tags = re.findall(r'<([a-zA-Z0-9_-]+)[^>]*class="[^"]*\bpg-api-only\b[^"]*"[^>]*>', html)
    assert len(api_only_tags) >= 3, (
        f"Expected at least 3 .pg-api-only elements, found {len(api_only_tags)}"
    )
    occurrences = [m for m in re.finditer(r'<[^>]*\bpg-api-only\b[^>]*>', html)]
    hidden_occurrences = [m for m in occurrences if re.search(r'\bhidden\b', m.group())]
    assert len(hidden_occurrences) == len(occurrences), (
        f"Expected all {len(occurrences)} .pg-api-only elements to have hidden, "
        f"found {len(hidden_occurrences)} with hidden"
    )


def test_setup_core_uses_hidden_property():
    """updateRouteMode must use the .hidden property, not style.display."""
    js = _slurp("api/webui/static/powergrader/setup_core.js")
    # Check hidden property assignments for route-dependent elements
    assert "aiOptions.hidden = !isAi" in js, (
        "updateRouteMode must set aiOptions.hidden = !isAi"
    )
    assert "rubricFast.hidden = isAi" in js, (
        "updateRouteMode must set rubricFast.hidden = isAi"
    )
    assert "el.hidden = mode !== 'assisted'" in js, (
        "updateRouteMode must set apiOnly el.hidden by mode"
    )
    assert "ackWrap.hidden = !isAi" in js, (
        "updateRouteMode must set ackWrap.hidden = !isAi"
    )


def test_setup_core_no_style_display_for_route_elements():
    """updateRouteMode must not use style.display for route-dependent elements."""
    js = _slurp("api/webui/static/powergrader/setup_core.js")
    # Isolate the updateRouteMode function body
    start = js.index("function updateRouteMode")
    end = js.index("function syncStartEnabled")
    body = js[start:end]
    forbidden = ['style.display']
    for pattern in forbidden:
        n = body.count(pattern)
        # Expected: style.display might still appear for non-route elements (e.g., mode label),
        # but not for aiOptions, rubricFast, apiOnly, ackWrap
        assert 'aiOptions.style.display' not in body, (
            "updateRouteMode must not use aiOptions.style.display"
        )
        assert 'rubricFast.style.display' not in body, (
            "updateRouteMode must not use rubricFast.style.display"
        )
        assert 'apiOnly' not in body or 'apiOnly.forEach' not in body or '.style.display' not in body[body.index('apiOnly'):body.index('apiOnly')+200], (
            "updateRouteMode must not use apiOnly el.style.display"
        )
    assert 'ackWrap.style.display' not in body, (
        "updateRouteMode must not use ackWrap.style.display"
    )


def test_powergrader_css_has_form_scoped_hidden_rule():
    """powergrader_setup.css must have #pg-start-form [hidden] { display: none !important; }."""
    css = _slurp("api/webui/static/powergrader_setup.css")
    assert "#pg-start-form [hidden]" in css, (
        "powergrader_setup.css missing #pg-start-form [hidden] rule"
    )
    assert "display: none !important" in css, (
        "powergrader_setup.css #pg-start-form [hidden] missing !important"
    )


# ── PowerGrader responsive layout contract (slice 2) ─────────────────

def test_powergrader_setup_extends_workbench_base():
    """PowerGrader setup must use the shared Workbench shell."""
    html = _slurp("api/webui/templates/powergrader_setup.html")
    assert '{% extends "workbench_base.html" %}' in html
    assert '{% block main_class %}ce-workbench-main pg-page{% endblock %}' in html
    assert 'class="ce-workbench-shell pg-workbench-shell"' in html


def test_powergrader_setup_session_module_load_order_and_uniqueness():
    """The setup namespace, sessions, core, and autoscore scripts load once in order."""
    html = _slurp("api/webui/templates/powergrader_setup.html")
    scripts = [
        "/static/powergrader_setup.js",
        "/static/powergrader/setup_sessions.js",
        "/static/powergrader/setup_core.js",
        "/static/powergrader/setup_autoscore.js",
    ]
    positions = []
    for script in scripts:
        assert html.count(script) == 1, f"Expected one script include: {script}"
        positions.append(html.index(script))
    assert positions == sorted(positions)


def test_powergrader_queue_extends_workbench_and_preserves_instrument_contract():
    """The grading queue uses Workbench composition without losing critical controls."""
    html = _slurp("api/webui/templates/powergrader_queue.html")
    assert '{% extends "workbench_base.html" %}' in html
    assert 'class="ce-instrument-shell pg-queue-instrument"' in html
    for critical_id in [
        "pg-bulk-push", "pg-privacy-strip", "pg-late-strip", "pg-packet-strip",
        "pg-submission-pane", "pg-grade-pane", "pg-score", "pg-feedback",
        "pg-save-next", "pg-push-one", "pg-kbd-a-hint", "pg-status-bar",
    ]:
        assert html.count(f'id="{critical_id}"') == 1, (
            f"Expected one queue control id={critical_id!r}"
        )

    scripts = [
        "/static/powergrader_queue.js",
        "/static/powergrader/queue_core.js",
        "/static/powergrader/queue_review.js",
        "/static/powergrader/queue_privacy.js",
        "/static/powergrader/queue_late_catchup.js",
        "/static/powergrader/queue_import.js",
    ]
    positions = []
    for script in scripts:
        assert html.count(script) == 1, f"Expected one script include: {script}"
        positions.append(html.index(script))
    assert positions == sorted(positions)


def test_powergrader_no_680px_inline_width():
    """Setup and session cards must not contain the 680px inline max-width."""
    html = _slurp("api/webui/templates/powergrader_setup.html")
    assert 'max-width:680px' not in html, (
        "Template must not contain inline max-width:680px on cards"
    )


def test_powergrader_critical_ids_exist_once():
    """Critical DOM IDs must each appear exactly once."""
    html = _slurp("api/webui/templates/powergrader_setup.html")
    for id_attr in ['pg-course', 'pg-assignment', 'pg-assignment-search',
                    'pg-assignment-group-by', 'pg-ai-options', 'pg-rubric-fast',
                    'pg-start-btn', 'pg-sessions-tbody']:
        pattern = f'id="{id_attr}"'
        count = html.count(pattern)
        assert count == 1, (
            f"Expected exactly 1 occurrence of id={id_attr!r}, found {count}"
        )


def test_powergrader_radio_values_exist():
    """All three mode radio values must be present."""
    html = _slurp("api/webui/templates/powergrader_setup.html")
    for val in ['fast', 'packet', 'assisted']:
        assert f'value="{val}"' in html, (
            f"Missing radio value '{val}' in template"
        )


def test_powergrader_labels_use_for():
    """Course, Assignment, and Modules must use explicit <label for>."""
    html = _slurp("api/webui/templates/powergrader_setup.html")
    assert '<label for="pg-course">' in html, (
        "Course label must use for=pg-course"
    )
    assert '<label for="pg-assignment">' in html, (
        "Assignment label must use for=pg-assignment"
    )
    assert '<label for="pg-assignment-group-by">' in html, (
        "Modules label must use for=pg-assignment-group-by"
    )


def test_powergrader_ack_before_start_button():
    """AI acknowledgment must appear after configuration sections and before start button."""
    html = _slurp("api/webui/templates/powergrader_setup.html")
    ack_idx = html.index('id="pg-ai-check"')
    btn_idx = html.index('id="pg-start-btn"')
    assert ack_idx < btn_idx, (
        "AI acknowledgment checkbox must appear before the start button"
    )


def test_powergrader_css_has_1180px_cap():
    """CSS must contain the 1180px page cap."""
    css = _slurp("api/webui/static/powergrader_setup.css")
    assert '1180px' in css, (
        "powergrader_setup.css missing 1180px page width cap"
    )


def test_powergrader_css_desktop_grids():
    """CSS must have desktop work-grid and AI-grid at 981px+ breakpoint."""
    css = _slurp("api/webui/static/powergrader_setup.css")
    assert '@media (min-width: 981px)' in css, (
        "CSS missing 981px+ desktop breakpoint"
    )
    assert '.pg-work-grid' in css, "CSS missing .pg-work-grid"
    assert '.pg-ai-grid' in css, "CSS missing .pg-ai-grid"


def test_powergrader_css_mobile_breakpoint():
    """CSS must have the 760px mobile breakpoint."""
    css = _slurp("api/webui/static/powergrader_setup.css")
    assert '@media (max-width: 760px)' in css, (
        "CSS missing 760px mobile breakpoint"
    )


def test_powergrader_css_intermediate_breakpoint():
    """CSS must have the 980px intermediate breakpoint."""
    css = _slurp("api/webui/static/powergrader_setup.css")
    assert '@media (max-width: 980px)' in css, (
        "CSS missing 980px intermediate breakpoint"
    )


def test_powergrader_mobile_search_resets_column_flex_basis():
    """The stacked mobile search control must retain normal input height."""
    css = _slurp("api/webui/static/powergrader_setup.css")
    mobile = css[css.index('@media (max-width: 760px)'):]
    match = re.search(
        r'\.pg-assignment-tools input\[type="search"\]\s*\{([^}]*)\}',
        mobile,
        re.DOTALL,
    )
    assert match and re.search(r'flex:\s*0\s+0\s+auto', match.group(1)), (
        "Mobile search must reset its desktop flex basis to avoid a 180px-tall input"
    )


def test_powergrader_fast_start_action_aligns_right():
    """The fast-mode action remains right-aligned when acknowledgment is hidden."""
    css = _slurp("api/webui/static/powergrader_setup.css")
    match = re.search(r'\.pg-start-primary\s*\{([^}]*)\}', css, re.DOTALL)
    assert match and re.search(r'margin-left:\s*auto', match.group(1)), (
        ".pg-start-primary must use automatic left margin on desktop"
    )


def test_powergrader_module_control_is_bounded_below_search_width():
    """Desktop Modules must not consume more space than assignment search."""
    css = _slurp("api/webui/static/powergrader_setup.css")
    search = re.search(
        r'\.pg-assignment-tools input\[type="search"\]\s*\{([^}]*)\}',
        css,
        re.DOTALL,
    )
    match = re.search(r'\.pg-assignment-group-control\s*\{([^}]*)\}', css, re.DOTALL)
    assert search and re.search(r'flex:\s*1\s+1\s+0', search.group(1)), (
        "Desktop search needs a zero flex basis so Search and Modules stay on one row"
    )
    assert match and re.search(r'max-width:\s*300px', match.group(1)), (
        "Desktop module control needs a bounded width so Search remains wider"
    )


def test_powergrader_folder_buttons_do_not_use_float_layout():
    """Folder actions must participate in the responsive flex/grid layout."""
    css = _slurp("api/webui/static/powergrader_setup.css")
    html = _slurp("api/webui/templates/powergrader_setup.html")
    assert 'float:' not in css, "PowerGrader folder actions must not use float layout"
    assert 'class="pg-control-head"' in html, (
        "PowerGrader template must group control labels and folder actions in flex headers"
    )


# ── Roster Workbench contract ────────────────────────────────────────

def test_roster_extends_workbench_and_loads_page_css_in_head():
    html = _slurp("api/webui/templates/roster.html")
    assert '{% extends "workbench_base.html" %}' in html
    assert '{% block main_class %}ce-workbench-main roster-page{% endblock %}' in html
    assert 'class="ce-workbench-shell roster-workbench-shell"' in html
    assert html.count('/static/roster_workbench.css?v={{ asset_v }}') == 1
    assert html.index('{% block head_extra %}') < html.index('/static/roster_workbench.css')


def test_roster_lenses_and_critical_controls_are_unique():
    html = _slurp("api/webui/templates/roster.html")
    for lens in ["students", "accommodations", "groups", "monitoring", "issues", "privacy"]:
        assert html.count(f'data-lens="{lens}"') == 1
    assert html.count('class="roster-lens-btn roster-filter-btn') == 5
    for critical_id in [
        "roster-course", "roster-refresh", "roster-open-canvas", "roster-search",
        "roster-group-set-picker", "roster-group-builder", "roster-bulk-bar",
        "roster-bulk-group", "roster-bulk-extra-days", "roster-table-card",
        "roster-table", "roster-table-body", "roster-select-all",
        "roster-group-labels-editor", "roster-safety-card", "roster-scrub-run",
        "roster-export-who", "roster-backup-vault",
    ]:
        assert html.count(f'id="{critical_id}"') == 1


def test_roster_scripts_load_once_in_feature_order():
    html = _slurp("api/webui/templates/roster.html")
    scripts = [
        "/static/roster.js",
        "/static/roster/table.js",
        "/static/roster/filters.js",
        "/static/roster/inline_edit.js",
        "/static/roster/group_state.js",
        "/static/roster/bulk.js",
        "/static/roster/groups.js",
        "/static/roster/safety.js",
    ]
    positions = []
    for script in scripts:
        assert html.count(script) == 1
        positions.append(html.index(script))
    assert positions == sorted(positions)


def test_roster_filters_owns_focus_query_and_lens_mapping():
    bootstrap = _slurp("api/webui/static/roster.js")
    filters = _slurp("api/webui/static/roster/filters.js")
    assert "focusTarget" not in bootstrap
    assert "applyFocusTarget" not in bootstrap
    assert "URLSearchParams(window.location.search)" not in bootstrap
    for focus in ['"extra-time"', 'groups: "groups"', 'monitoring: "monitoring"', 'issues: "issues"', 'privacy: "privacy"']:
        assert focus in filters
    assert "history.replaceState" in filters
    assert "shell.dataset.rosterLens" in filters
