"""The `/glass` page: every state of the day, rendered against a frozen clock.

`?at=<ISO8601>` pins the instant for the whole render, which is what makes these
tests possible without waiting for 12:13 to come around. The schedule and plan
below are a made-up school in 2099, supplied by monkeypatching the two loaders,
so no workspace is read and no real bell times exist anywhere in this file.

The structural checks at the end read source rather than rendered output. They
guard the invariants that cannot be measured from HTML text: that nothing
touchable sits outside the tray, that the tray's height is one declared value,
and that this page never reaches for a model, the mirror, the vault, or the
network.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.glass.schema import DAY_PLAN_FORMAT, parse_day_plan
from api.schedule.loader import parse_bell_schedule
from api.schedule.models import SCHEDULE_FORMAT
from api.webui.routes import glass as glass_routes
from api.webui.server import app

ROOT = Path(__file__).resolve().parents[3]
WEDNESDAY = date(2099, 9, 16)
FRIDAY = date(2099, 9, 18)


def _schedule_data(**overrides):
    data = {
        "format": SCHEDULE_FORMAT,
        "school": "Mockingbird Junior High",
        "timezone": "America/Chicago",
        "day_types": {
            "bobcat_hour": {
                "label": "Bobcat Hour Day",
                "blocks": [
                    {"id": "p1", "kind": "class", "label": "1st Period",
                     "start": "08:30", "end": "09:19"},
                    {"id": "p2", "kind": "class", "label": "2nd Period",
                     "start": "09:25", "end": "10:14"},
                    {"id": "bobcat", "kind": "bobcat_hour", "label": "Bobcat Hour",
                     "start": "11:15", "end": "12:15",
                     "sub_blocks": {"mode": "concurrent", "blocks": []}},
                    {"id": "p6", "kind": "class", "label": "6th Period",
                     "start": "14:11", "end": "15:00"},
                ],
            },
            "friday": {
                "label": "Friday",
                "blocks": [
                    {"id": "p1", "kind": "class", "label": "1st Period",
                     "start": "08:30", "end": "09:24"},
                    {"id": "p4", "kind": "class", "label": "4th Period",
                     "start": "11:30", "end": "13:00",
                     "sub_blocks": {"mode": "sequential", "blocks": [
                         {"id": "p4a", "kind": "lunch", "label": "4th Period / A Lunch",
                          "start": "11:30", "end": "12:15"},
                         {"id": "p4b", "kind": "lunch", "label": "4th Period / B Lunch",
                          "start": "12:15", "end": "13:00"},
                     ]}},
                ],
            },
        },
        "weekday_default": {
            "0": "bobcat_hour", "1": "bobcat_hour",
            "2": "bobcat_hour", "3": "bobcat_hour", "4": "friday",
        },
    }
    data.update(overrides)
    return data


def _plan_data(on: date, **overrides):
    data = {
        "format": DAY_PLAN_FORMAT,
        "date": on.isoformat(),
        "school_wide": {
            "events": [{"label": "Picture day", "when": "Thursday"}],
            "bobcat_hour_offerings": [{"label": "Robotics Club", "location": "Rm 214"}],
        },
        "teacher": {"bobcat_hour_here": {"label": "Essay retakes", "location": "Rm 108"}},
        "sections": {
            "p1": {
                "learning_goal": "Explain how point of view shapes what a reader knows",
                "success_criteria": ["Name the narrator", "Quote one clue"],
                "work": [{"name": "Point of view sort", "detail": "Finish page 2"}],
                "banner": ["Turn in your reading log"],
            },
            "p4": {"learning_goal": "Revise one paragraph for a clearer claim"},
        },
    }
    data.update(overrides)
    return data


@pytest.fixture
def glass(monkeypatch):
    """A configured app with a fictional schedule and one fictional day plan."""
    state = {
        "schedule": parse_bell_schedule(_schedule_data()),
        "schedule_notes": [],
        "plans": {},
        "no_school": frozenset(),
    }
    for on in (WEDNESDAY, FRIDAY):
        state["plans"][on] = parse_day_plan(_plan_data(on))

    monkeypatch.setattr(glass_routes.config, "token_is_set", lambda: True)
    monkeypatch.setattr(
        glass_routes.config, "get_canvas_base", lambda: "https://canvas.example.test"
    )
    monkeypatch.setattr(
        glass_routes.loader, "discover_bell_schedule",
        lambda: (state["schedule"], list(state["schedule_notes"])),
    )
    monkeypatch.setattr(
        glass_routes.store, "load_day_plan",
        lambda on: (
            (state["plans"].get(on), [])
            if on in state["plans"]
            else (None, [f"No plan written for {on.isoformat()}, so the focus area stays empty."])
        ),
    )
    monkeypatch.setattr(
        glass_routes.schedule_calendar, "no_school_dates",
        lambda date_from, date_to: state["no_school"],
    )
    return state


def _get(url: str) -> str:
    client = TestClient(app, base_url="http://127.0.0.1:8765")
    response = client.get(url)
    assert response.status_code == 200, url
    return response.text


def _blob(text: str) -> dict:
    match = re.search(
        r'<script id="glass-data" type="application/json">(.*?)</script>',
        text, re.DOTALL,
    )
    assert match, "the page must carry its render blob as JSON"
    return json.loads(match.group(1))


def _strip_now(text: str) -> str:
    """The block id the day strip currently lights."""
    for item in re.findall(r'<li class="glass-strip__item[^"]*"\s+data-glass-block="[^"]+"', text):
        if "glass-strip__item--now" in item:
            return re.search(r'data-glass-block="([^"]+)"', item).group(1)
    return ""


# ------------------------------------------------------------ frozen clock


def test_a_mid_block_moment_renders_label_countdown_progress_and_highlight(glass):
    text = _get("/glass?at=2099-09-16T08:40:00")

    assert "Mockingbird Junior High" in text
    assert "Bobcat Hour Day" in text
    assert ">1st Period<" in text
    assert "39 min left" in text
    assert 'data-percent="20"' in text
    assert _strip_now(text) == "p1"
    assert "Explain how point of view shapes what a reader knows" in text
    assert "Point of view sort" in text
    assert _blob(text)["clock_frozen"] is True


def test_a_passing_period_renders_its_countdown_and_lights_nothing(glass):
    text = _get("/glass?at=2099-09-16T09:22:00")

    assert "3 min to 2nd Period" in text
    assert "Passing period" in text
    assert ">3:00<" in text
    assert _strip_now(text) == ""


def test_before_school_counts_down_to_first_bell(glass):
    text = _get("/glass?at=2099-09-16T07:55:00")

    assert "35 min to first bell" in text
    assert _strip_now(text) == ""


def test_after_school_says_so_without_a_countdown(glass):
    text = _get("/glass?at=2099-09-16T15:30:00")

    blob = _blob(text)
    assert blob["current"]["placement"] == "after_school"
    assert blob["current"]["remaining_text"] == ""
    assert _strip_now(text) == ""


def test_lunch_inside_a_period_lights_the_parent_and_labels_the_half(glass):
    text = _get("/glass?at=2099-09-18T12:30:00")

    assert "4th Period / B Lunch" in text
    assert _strip_now(text) == "p4"
    assert 'data-percent="33"' in text


def test_a_weekend_renders_a_working_page_rather_than_a_blank_one(glass):
    text = _get("/glass?at=2099-09-19T10:00:00")

    assert "No school" in text
    assert 'id="glass-tray"' in text
    assert _blob(text)["blocks"] == []


def test_a_calendar_no_school_date_closes_the_day(glass):
    glass["no_school"] = frozenset({WEDNESDAY})
    text = _get("/glass?at=2099-09-16T08:40:00")

    assert _blob(text)["is_school_day"] is False


def test_without_at_the_page_uses_the_real_clock_and_keeps_ticking(glass):
    text = _get("/glass")

    assert _blob(text)["clock_frozen"] is False


def test_an_unreadable_at_value_falls_back_to_the_real_clock(glass):
    text = _get("/glass?at=half+past+lunch")

    assert _blob(text)["clock_frozen"] is False


# ------------------------------------------------------- Bobcat Hour pane


def test_the_pane_reads_today_in_the_morning_and_lists_offerings(glass):
    text = _get("/glass?at=2099-09-16T08:40:00")

    assert "Today during Bobcat Hour" in text
    assert "Robotics Club" in text
    assert "Rm 214" in text
    assert "Essay retakes" in text


def test_a_friday_pane_resolves_forward_to_monday(glass):
    text = _get("/glass?at=2099-09-18T09:00:00")

    assert "Monday during Bobcat Hour" in text
    # Monday's plan is not written, so the pane says where offerings come from
    # rather than showing Friday's list under Monday's heading. The apostrophe
    # arrives escaped, which is the autoescaping doing its job.
    assert "Offerings post with that day" in text
    assert "Robotics Club" not in text


def test_the_pane_the_browser_flips_to_travels_with_the_page(glass):
    blob = _blob(_get("/glass?at=2099-09-16T08:40:00"))

    assert blob["bobcat_hour"]["is_today"] is True
    assert blob["bobcat_hour_after"]["heading"] == "Tomorrow during Bobcat Hour"


# ------------------------------------------------------------ missing data


def test_a_missing_plan_renders_a_working_page_with_a_note(glass):
    text = _get("/glass?at=2099-09-17T08:40:00")

    assert "No plan for today" in text
    assert ">1st Period<" in text
    assert "No plan written for 2099-09-17" in text
    assert _strip_now(text) == "p1"


def test_a_sample_only_schedule_renders_and_is_marked_as_sample(glass, monkeypatch):
    sample = parse_bell_schedule(_schedule_data(sample=True))
    monkeypatch.setattr(
        glass_routes.loader, "discover_bell_schedule",
        lambda: (sample, ["These are sample times from a made-up school, not your bells."]),
    )
    text = _get("/glass?at=2099-09-16T08:40:00")

    assert "Sample schedule" in text
    assert ">1st Period<" in text
    assert _blob(text)["is_sample"] is True


def test_no_schedule_at_all_renders_a_page_with_a_note(glass, monkeypatch):
    monkeypatch.setattr(
        glass_routes.loader, "discover_bell_schedule",
        lambda: (None, ["No bell schedule yet. Copy the template and fill in your bells."]),
    )
    text = _get("/glass?at=2099-09-16T08:40:00")

    assert "No bell schedule yet" in text
    assert 'id="glass-tray"' in text
    assert _blob(text)["blocks"] == []


def test_over_length_text_reaches_the_page_already_clamped(glass):
    glass["plans"][WEDNESDAY] = parse_day_plan(_plan_data(
        WEDNESDAY,
        school_wide={
            "bobcat_hour_offerings": [{"label": "L" * 200, "location": "C" * 200}],
            "events": [],
        },
        sections={"p1": {
            "learning_goal": "G" * 400,
            "success_criteria": ["S" * 200],
            "work": [{"name": "N" * 200, "detail": "D" * 200}],
        }},
    ))
    blob = _blob(_get("/glass?at=2099-09-16T08:40:00"))

    assert "G" * 200 not in _get("/glass?at=2099-09-16T08:40:00")
    plan = blob["current"]["plan"]
    assert len(plan["learning_goal"]) == 90
    assert len(plan["success_criteria"][0]) == 40
    assert len(plan["work"][0]["name"]) == 34
    assert len(plan["work"][0]["detail"]) == 44
    offering = blob["bobcat_hour"]["offerings"][0]
    assert len(offering["label"]) == 30
    assert len(offering["location"]) == 12


# ------------------------------------------------------- one title per page


def test_the_page_title_the_nav_word_and_the_heading_all_read_glass(glass):
    text = _get("/glass?at=2099-09-16T08:40:00")
    header = (ROOT / "api/webui/templates/layouts/_app_header.html").read_text(encoding="utf-8")

    assert "<title>Glass - Canvas Expert</title>" in text
    assert ">Glass</h1>" in text
    assert '>Glass</a>' in header
    assert 'href="/glass"' in header


# -------------------------------------------------------- structural source


def _slurp(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


GLASS_JS = (
    "api/webui/static/glass/widgets.js",
    "api/webui/static/glass/runtime.js",
    "api/webui/static/glass/timer.js",
)


def test_the_page_sits_on_the_display_family():
    template = _slurp("api/webui/templates/glass.html")
    layout = _slurp("api/webui/templates/layouts/display.html")

    assert '{% extends "layouts/display.html" %}' in template
    assert '{% extends "base.html" %}' in layout
    assert 'data-ce-layout="display"' in layout
    assert "{% block app_header %}{% endblock %}" in layout
    assert layout.count("<main") == 0  # base.html owns the single <main>
    assert "ce-display" in _slurp("api/webui/static/ui/layouts.css")


def test_nothing_touchable_sits_outside_the_tray():
    """Reach governs the layout, so the tray is the only interactive region.

    An exit or navigation control would be an interactive element above the
    bottom third, which is why the page deliberately has none. The teacher uses
    the browser.
    """
    template = _slurp("api/webui/templates/glass.html")
    body = template[template.index("{% block primary %}"):template.index("{% endblock %}\n\n{% block display_scripts %}")]
    tray_at = body.index('id="glass-tray"')

    assert body.count("<button") > 0
    for match in re.finditer(r"<(button|a|input|select|textarea|summary)\b", body):
        assert match.start() > tray_at, f"interactive <{match.group(1)}> outside the tray"
    # Every interactive element carries the shared hook the geometry check selects on.
    assert body.count("<button") == body.count('data-ce-hook="glass-touch"')
    assert "href=" not in body


def test_the_tray_height_is_one_declared_value_and_both_states_use_it():
    css = _slurp("api/webui/static/pages/glass.css")
    template = _slurp("api/webui/templates/glass.html")

    assert css.count("--glass-tray-height:") == 1
    assert "height: var(--glass-tray-height);" in css
    # Two sibling states, exactly one shown, inside a fixed-height container.
    assert template.count('class="glass-tray__state"') == 2
    assert 'id="glass-tray-rest"' in template
    assert 'id="glass-tray-running"' in template


def test_the_bobcat_pane_elements_are_always_present_so_the_flip_can_fill_them():
    """The pane swaps itself from today to tomorrow on the clock.

    Rendering its heading, its times, and its note conditionally left the browser
    with no element to write into after the block ended, which is how a pane can
    end up showing yesterday's list under tomorrow's heading.
    """
    template = _slurp("api/webui/templates/glass.html")

    for element_id in ("glass-bobcat-heading", "glass-bobcat-when", "glass-bobcat-note"):
        assert template.count(f'id="{element_id}"') == 1, element_id
    assert "{% if not glass.bobcat_hour.available %}hidden{% endif %}" in template
    assert "{% if not glass.bobcat_hour.note %}hidden{% endif %}" in template


def test_the_events_pane_collapses_once_its_last_item_is_shed():
    template = _slurp("api/webui/templates/glass.html")
    runtime = _slurp("api/webui/static/glass/runtime.js")

    assert 'id="glass-events-pane"' in template
    assert "eventsPane" in runtime
    assert "function shedPanes" in runtime
    # The Bobcat Hour list is never shed, whatever the rail is short of.
    assert "shed(el.bobcatList)" not in runtime
    assert "yieldItems(el.bobcatList" not in runtime


def test_shedding_is_driven_by_the_priority_not_by_each_pane_noticing_itself():
    """Events yield to the Bobcat Hour pane, then work does.

    The first version of this asked each list whether it was overflowing, which
    satisfied the rule only by accident: with a long offering list, events was
    never itself overflowing, so it never gave anything up and the Bobcat Hour
    pane absorbed the whole shortfall by clipping. The driver has to be whether
    the pane that holds its ground fits.
    """
    runtime = _slurp("api/webui/static/glass/runtime.js")
    order = runtime.index("var bobcatFits")

    assert "function fits(list)" in runtime
    assert "yieldItems(el.events, bobcatFits)" in runtime
    assert "yieldItems(el.work, bobcatFits)" in runtime
    # Events yields before work does.
    assert runtime.index("yieldItems(el.events, bobcatFits)") < runtime.index(
        "yieldItems(el.work, bobcatFits)"
    )
    assert order < runtime.index("yieldItems(el.events, bobcatFits)")


def test_the_bobcat_pane_owns_the_rails_flexible_row():
    """The pane that holds its ground is the one that grows.

    With the flexible row under events instead, an item shed from events handed
    its space to a track with nothing in it, so the freed room never reached the
    pane it was freed for.
    """
    css = _slurp("api/webui/static/pages/glass.css")

    assert "grid-template-rows: auto minmax(0, 1fr) auto;" in css
    assert "grid-template-rows: minmax(0, auto) auto minmax(0, 1fr);" not in css
    # The list fills the pane, so a short final rotation page cannot shrink it.
    assert "flex: 1 1 auto;" in css


# --------------------------------------------------------- a long list rotates


def test_a_long_offering_list_rotates_rather_than_being_cut_off():
    template = _slurp("api/webui/templates/glass.html")
    runtime = _slurp("api/webui/static/glass/runtime.js")

    assert template.count('id="glass-bobcat-more"') == 1
    for name in ("applyBobcatPage", "fittedRowCount", "rotateBobcatIfDue", "pageLabel"):
        assert name in runtime, name
    # Shedding settles how much rail the pane gets, then rotation picks a page
    # inside it. The other order would measure capacity against the wrong height.
    assert runtime.index("collapseEvents();\n    applyBobcatPage();") > 0


def test_rotation_does_not_start_when_the_whole_list_already_fits():
    """Most days fit, and motion with nothing to reveal is only noise."""
    runtime = _slurp("api/webui/static/glass/runtime.js")

    assert "if (!items.length || capacity >= items.length)" in runtime
    assert "if (day.clock_frozen || bobcatPages <= 1) return;" in runtime


def test_rotation_rides_the_existing_tick_and_has_its_own_interval():
    """No second loop racing the clock, and no pulsing in step with the banner."""
    runtime = _slurp("api/webui/static/glass/runtime.js")

    assert "var BOBCAT_ROTATE_MS = 17000;" in runtime
    assert "var BANNER_MS = 12000;" in runtime
    # Rotation is advanced from paint(), not from a setInterval of its own.
    assert "rotateBobcatIfDue();" in runtime
    assert runtime.count("window.setInterval") == 2, (
        "the clock and the banner are the only two loops on this page"
    )
    assert "setInterval(rotateBobcatIfDue" not in runtime
    assert "setTimeout(rotateBobcatIfDue" not in runtime


def test_rotation_is_parked_on_a_first_page_under_a_frozen_clock():
    """`?at=` exists so a state can be looked at and measured.

    A pane that kept moving under a pinned instant would make every measurement
    of that instant a different answer, which turns a geometry suite flaky.
    """
    runtime = _slurp("api/webui/static/glass/runtime.js")
    body = runtime[runtime.index("function rotateBobcatIfDue"):]
    guard = body[: body.index("}")]

    assert "day.clock_frozen" in guard
    # The page index only ever moves through the one advance path.
    assert runtime.count("bobcatPage = (bobcatPage + 1)") == 1


def test_the_page_indication_is_quiet_text_and_never_a_control():
    """Nothing interactive may appear this high on the screen (AC 7)."""
    template = _slurp("api/webui/templates/glass.html")
    css = _slurp("api/webui/static/pages/glass.css")
    marker = '<p class="glass-pane__page" id="glass-bobcat-more" hidden></p>'

    assert marker in template
    # It ships hidden, and the browser owns whether it is shown.
    assert "glass-pane__page" in css
    element = template[template.index(marker):template.index(marker) + len(marker)]
    assert "data-ce-hook" not in element
    assert "onclick" not in element


def test_rotation_survives_a_new_offering_list_and_a_bell():
    runtime = _slurp("api/webui/static/glass/runtime.js")

    # A rebuilt list starts at its first page.
    assert "bobcatPage = 0;\n    bobcatRotatedAt = 0;" in runtime
    # A bell can reshape the rail, so the page is clamped rather than assumed.
    assert "if (bobcatPage >= bobcatPages) bobcatPage = 0;" in runtime
    # A different offering count changes what the rail has to fit.
    assert "if (changed || bobcatRebuilt) shedPanes();" in runtime


def test_the_rotation_page_is_live_state_the_server_never_sees():
    """Locked decision 2 and spec D2: browser only, lost on refresh."""
    view_source = _slurp("api/glass/view.py")
    runtime = _slurp("api/webui/static/glass/runtime.js")

    for absent in ("bobcat_page", "rotation", "page_size"):
        assert absent not in view_source, absent
    assert "bobcatRotation" in runtime
    for banned in ("localStorage", "sessionStorage", "indexedDB"):
        assert banned not in runtime, banned


def test_hit_targets_have_a_single_declared_floor():
    css = _slurp("api/webui/static/pages/glass.css")

    assert css.count("--glass-touch-min:") == 1
    assert "min-width: var(--glass-touch-min);" in css


def test_reset_is_set_apart_and_asks_a_second_time():
    template = _slurp("api/webui/templates/glass.html")
    timer = _slurp("api/webui/static/glass/timer.js")

    assert 'class="glass-tray__spacer"' in template
    assert "glass-touch--apart" in template
    assert "Tap again to reset" in timer
    assert "glass-tray__spacer" in _slurp("api/webui/static/pages/glass.css")


def test_the_under_two_minutes_state_uses_the_shared_danger_token():
    css = _slurp("api/webui/static/pages/glass.css")
    timer = _slurp("api/webui/static/glass/timer.js")

    assert "var(--ce-danger)" in css
    assert "glass-timer--urgent" in css
    assert "URGENT_SECONDS = 120" in timer


def test_the_widget_contract_is_a_registration_seam_with_one_widget_on_it():
    widgets = _slurp("api/webui/static/glass/widgets.js")
    timer = _slurp("api/webui/static/glass/timer.js")

    for name in ("register", "summon", "dismiss", "showTray", "notifyPeriodChange"):
        assert f"{name}:" in widgets, name
    for declared in ("name:", "launcherLabel:", "claimsFocus:", "trayStates:", "onPeriodChange:"):
        assert declared in timer, declared
    assert timer.count("widgets.register(") == 1
    # No second widget, however small it looks once the tray exists.
    for absent in ("picker", "dice", "spinner", "scoreboard", "noise", "group maker"):
        assert absent not in timer.lower(), absent


def test_the_page_never_polls_and_never_reaches_for_anything_live():
    """No fetches, no endpoints, no addresses. The day arrives once, in the page."""
    for relative in GLASS_JS:
        js = _slurp(relative)
        for banned in (
            "fetch(", "XMLHttpRequest", "WebSocket", "EventSource",
            "navigator.send", "import(", "requestAnimationFrame",
        ):
            assert banned not in js, f"{relative} uses {banned}"
        for banned in ("/api/", "http://", "https://", "openrouter"):
            assert banned not in js.lower(), f"{relative} mentions {banned}"


def test_live_state_is_never_persisted_or_sent():
    for relative in GLASS_JS:
        js = _slurp(relative)
        for banned in ("localStorage", "sessionStorage", "indexedDB", "document.cookie"):
            assert banned not in js, f"{relative} uses {banned}"


def test_glass_python_never_calls_a_model_or_writes_to_canvas():
    for relative in ("api/glass/view.py", "api/webui/routes/glass.py"):
        source = _slurp(relative).lower()
        for banned in ("openrouter", "requests.", "httpx", "canvas_client", "operation_ledger"):
            assert banned not in source, f"{relative} mentions {banned}"


def test_shared_component_classes_are_not_glass_javascript_hooks():
    for relative in GLASS_JS:
        js = _slurp(relative)
        for selector in (".ce-panel", ".ce-rail", ".ce-btn", ".ce-shell"):
            assert selector not in js, f"{relative} selects {selector}"
