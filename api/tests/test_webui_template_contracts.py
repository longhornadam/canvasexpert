"""Source-contract tests for WebUI templates and client JS.

These guard against specific P1 regression modes. They read source files
directly — no live Canvas, no server, no student data.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _slurp(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


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


def test_dashboard_has_start_a_job():
    """dashboard.html must contain 'Start a job' section heading."""
    html = _slurp("api/webui/templates/dashboard.html")
    assert "Start a job" in html, (
        "Dashboard missing 'Start a job' section heading"
    )


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
    assert 'id="pg-ai-options" hidden' in html, (
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
    for tag in api_only_tags:
        count = html.count(f'class="pg-api-only" hidden')
        count2 = html.count(f'class="pg-api-only pg-api-only" hidden')  # unlikely but check
        count3 = html.count('pg-api-only" hidden')  # any class ending with pg-api-only
        # Better: just check each occurrence
    # Count properly
    occurrences = [m for m in re.finditer(r'<[^>]*\bpg-api-only\b[^>]*>', html)]
    hidden_occurrences = [m for m in occurrences if 'hidden' in m.group()]
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