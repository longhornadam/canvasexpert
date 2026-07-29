"""Glass, measured at real size in a real browser.

Three acceptance criteria in the Glass brief are about rendered geometry, and
geometry cannot be read out of source. Reading the stylesheet tells you that a
tap target declares `min-width: 10.5vw`; it does not tell you what the browser
did with that after flex sizing, a media query, and a font that turned out
wider than expected. So this module drives a real page in a real browser and
measures boxes:

* AC 6, no element overflows its container in any state, including a Bobcat
  Hour pane at maximum offering count, with every character budget exceeded.
* AC 7, every interactive element sits inside the bottom third of the screen
  and is at least 9% of screen width.
* AC 9, the tray's rendered height is identical at rest and while running, so
  nothing above it moves when a timer starts or stops.

These tests skip rather than fail when Playwright or its Chromium build is
absent, matching the one existing browser-driving test in this repo
(`engine/tests/unit/test_physical_html_parity.py`). A machine without browsers
is a machine that cannot answer the question, which is different from a page
that fails it. The skip message names the command that enables them.

The page is served by a real subprocess rather than a test client, because the
whole point is a browser laying out a page, and because the page reads its
schedule and its day plan off the workspace. Two environment variables carry
the isolation across the process boundary: `LOCALAPPDATA` decides where machine
config lives (see `api/runtime_paths.py`), and the `workspace_path` written into
that config decides where the workspace lives. The subprocess also swaps in a
fictional credential store, so the onboarding gate is satisfied without reading
or writing this machine's real Canvas token.

Every number the assertions compare against is imported or derived. The
character budgets come from `api.glass.schema`, the bottom third and the 9%
floor come from the brief, and the viewport sizes are the two 16:10 shapes a
classroom projector actually runs at.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

import pytest

from api.glass.schema import (
    BUDGET_LEARNING_GOAL,
    BUDGET_OFFERING_LABEL,
    BUDGET_OFFERING_LOCATION,
    BUDGET_SUCCESS_CRITERION,
    BUDGET_WORK_DETAIL,
    BUDGET_WORK_NAME,
    DAY_PLAN_FORMAT,
)
from api.schedule.models import SCHEDULE_FORMAT

sync_api = pytest.importorskip(
    "playwright.sync_api", reason="playwright is not installed"
)

REPO_ROOT = Path(__file__).resolve().parents[3]
API_DIR = REPO_ROOT / "api"

# A Wednesday in a school year that does not exist, at a moment inside first
# period, so the focus slot holds a learning goal and the Bobcat Hour pane is
# still looking at today.
FROZEN_DATE = date(2099, 9, 16)
FROZEN_AT = "2099-09-16T09:00:00"

# The two 16:10 shapes worth measuring: a classroom laptop and the projector.
VIEWPORTS = ((1280, 800), (1920, 1200))

# Reach, from the brief. Everything touchable lives in the bottom third and no
# hit target is smaller than 9% of screen width.
BOTTOM_THIRD = 2.0 / 3.0
MIN_TOUCH_WIDTH_FRACTION = 0.09

# Subpixel rounding: a box laid out at a fractional device pixel can report a
# scroll size one pixel larger than its client size without anything being
# clipped, so every geometry comparison carries a single pixel of slack.
TOLERANCE_PX = 1.0

# How far past its budget each string is written. The renderer has to clamp,
# and a clamped string is one character shorter than the raw one only when the
# overrun is real, so this is comfortably more than one.
OVERRUN_CHARS = 25

# The schema declares no cap on Bobcat Hour offerings, so "maximum offering
# count" has to be stated here rather than imported. It is set deliberately
# past anything a junior high would publish for one lunch hour, because with no
# cap in the schema the state worth measuring is an offering list longer than
# the pane, which is the only version of "maximum" that means anything.
MAX_OFFERINGS = 24

# What the pane has to show at that maximum. The Bobcat Hour pane holds its
# ground while events shed items first (brief §5.5), so its capacity is a
# property of the layout and worth pinning: the shipped fictional sample's five
# offerings plus this room's own entry, all of them fully inside the pane. The
# measured capacity is larger than this floor at both viewports and the test
# prints it, so a change that eats into the pane shows up as a smaller number
# well before it starts hiding a realistic slate.
VISIBLE_ITEM_FLOOR = 6

# The layout frame: the containers that must never have overflow to hide,
# whatever the content does. Leaf text runs are deliberately absent, because
# `text-overflow: ellipsis` on a nowrap line reports a scroll width larger than
# its client width by design, and so are the pane lists, because shedding whole
# items when the rail runs short is the brief's own answer to a tight screen
# (§5.5). What must never happen is the frame itself carrying hidden overflow,
# which is what would push a pane off the bottom of a projector.
FRAME_SELECTORS = (
    ".glass",
    ".glass-rail",
    ".glass-body",
    "#glass-focus",
    "#glass-focus-rest",
    ".glass-panes",
    ".glass-pane",
    ".glass-strip",
    "#glass-tray",
    ".glass-tray__state",
    ".glass-tray__row",
)

# Ask the browser for one JSON structure per question rather than a round trip
# per element: fewer moving parts, and every number in a failure message comes
# from the same layout pass.
_MEASURE_FRAME = """
(selectors) => {
  const out = [];
  selectors.forEach((selector) => {
    document.querySelectorAll(selector).forEach((el, index) => {
      if (el.offsetParent === null && el !== document.body) return;
      out.push({
        selector: selector,
        index: index,
        id: el.id || "",
        scrollWidth: el.scrollWidth,
        clientWidth: el.clientWidth,
        scrollHeight: el.scrollHeight,
        clientHeight: el.clientHeight,
      });
    });
  });
  return {
    boxes: out,
    docScrollWidth: document.documentElement.scrollWidth,
    docScrollHeight: document.documentElement.scrollHeight,
    innerWidth: window.innerWidth,
    innerHeight: window.innerHeight,
  };
}
"""

# Only the visible tray state is measured. Both states are always in the DOM
# and one carries `hidden`, so `offsetParent === null` is what tells them apart.
_MEASURE_TOUCH = """
() => {
  const all = Array.prototype.slice.call(
    document.querySelectorAll('[data-ce-hook="glass-touch"]')
  );
  const visible = all.filter((el) => el.offsetParent !== null);
  return {
    total: all.length,
    targets: visible.map((el) => {
      const rect = el.getBoundingClientRect();
      return {
        label: (el.textContent || "").trim().slice(0, 40),
        top: rect.top,
        bottom: rect.bottom,
        left: rect.left,
        right: rect.right,
        width: rect.width,
        height: rect.height,
      };
    }),
    innerWidth: window.innerWidth,
    innerHeight: window.innerHeight,
  };
}
"""

_MEASURE_TRAY = """
() => {
  const tray = document.getElementById("glass-tray");
  const focus = document.getElementById("glass-focus");
  const trayRect = tray.getBoundingClientRect();
  const focusRect = focus.getBoundingClientRect();
  const rest = document.getElementById("glass-tray-rest");
  const running = document.getElementById("glass-tray-running");
  return {
    trayHeight: trayRect.height,
    trayTop: trayRect.top,
    focusTop: focusRect.top,
    focusHeight: focusRect.height,
    restVisible: rest.offsetParent !== null,
    runningVisible: running.offsetParent !== null,
  };
}
"""

_MEASURE_TEXT = """
() => {
  const text = (el) => (el && el.textContent ? el.textContent.trim() : "");
  const list = (selector) =>
    Array.prototype.slice.call(document.querySelectorAll(selector)).map(text);
  return {
    goal: text(document.getElementById("glass-goal")),
    criteria: list("#glass-criteria li"),
    workNames: list("#glass-work .glass-pane__name"),
    workDetails: list("#glass-work .glass-pane__detail"),
    offeringNames: list(
      "#glass-bobcat-list li:not(.glass-pane__item--here) .glass-pane__name"
    ),
    offeringLocations: list(
      "#glass-bobcat-list li:not(.glass-pane__item--here) .glass-pane__detail"
    ),
    hereName: text(
      document.querySelector(
        "#glass-bobcat-list .glass-pane__item--here .glass-pane__name"
      )
    ),
    bobcatItems: document.querySelectorAll("#glass-bobcat-list li").length,
    heading: text(document.getElementById("glass-bobcat-heading")),
    nowLabel: text(
      document.querySelector(".glass-strip__item--now .glass-strip__label")
    ),
  };
}
"""

_MEASURE_BOBCAT = """
() => {
  const pane = document.querySelector(".glass-pane--bobcat");
  const panes = document.querySelector(".glass-panes");
  const listEl = document.getElementById("glass-bobcat-list");
  const paneRect = pane.getBoundingClientRect();
  const panesRect = panes.getBoundingClientRect();
  const listRect = listEl.getBoundingClientRect();
  const items = Array.prototype.slice.call(listEl.querySelectorAll("li"));
  let fullyVisible = 0;
  items.forEach((li) => {
    const rect = li.getBoundingClientRect();
    if (rect.top >= listRect.top - 1 && rect.bottom <= listRect.bottom + 1) {
      fullyVisible += 1;
    }
  });
  return {
    items: items.length,
    fullyVisible: fullyVisible,
    paneTop: paneRect.top,
    paneBottom: paneRect.bottom,
    paneHeight: paneRect.height,
    panesTop: panesRect.top,
    panesBottom: panesRect.bottom,
    panesScrollHeight: panes.scrollHeight,
    panesClientHeight: panes.clientHeight,
  };
}
"""

# Run in the server subprocess. `sys.argv` carries the paths so nothing has to
# be pasted into this source as a literal.
_SERVER_BOOTSTRAP = '''
import sys

repo_root, api_dir, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
sys.path.insert(0, api_dir)
sys.path.insert(0, repo_root)

import keyring
from keyring.backend import KeyringBackend


class FictionalKeyring(KeyringBackend):
    """A credential store that exists only inside this process.

    The onboarding gate asks config.token_is_set(), which reads the machine
    credential store. A measuring server has no business reading a teacher's
    real token, and no business writing one either, so this answers with a
    fictional string and forgets whatever it is told.
    """

    priority = 1

    def get_password(self, service, username):
        return "fictional-glass-geometry-token"

    def set_password(self, service, username, password):
        return None

    def delete_password(self, service, username):
        return None


keyring.set_keyring(FictionalKeyring())

import uvicorn

uvicorn.run(
    "webui.server:app",
    host="127.0.0.1",
    port=port,
    lifespan="off",
    log_level="warning",
)
'''


# ------------------------------------------------------------- fictional content


def _over_length(budget: int, seed: str) -> str:
    """`seed` repeated past `budget`, so the renderer has to clamp it."""
    repeated = ((seed + " ") * (budget // len(seed) + 3)).strip()
    text = repeated[: budget + OVERRUN_CHARS]
    assert len(text) > budget, seed
    return text


def _schedule_data() -> dict:
    """A made-up school's bells. No `sample` key, so the loader prefers it."""
    return {
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
                    {"id": "p3", "kind": "class", "label": "3rd Period",
                     "start": "10:20", "end": "11:09"},
                    {"id": "bobcat", "kind": "bobcat_hour", "label": "Bobcat Hour",
                     "start": "11:15", "end": "12:15",
                     "sub_blocks": {"mode": "concurrent", "blocks": []}},
                    {"id": "p5", "kind": "class", "label": "5th Period",
                     "start": "12:21", "end": "13:10"},
                    {"id": "p6", "kind": "class", "label": "6th Period",
                     "start": "13:16", "end": "14:05"},
                    {"id": "p7", "kind": "class", "label": "7th Period",
                     "start": "14:11", "end": "15:00"},
                ],
            },
        },
        "weekday_default": {
            "0": "bobcat_hour", "1": "bobcat_hour", "2": "bobcat_hour",
            "3": "bobcat_hour", "4": "bobcat_hour",
        },
    }


def _plan_data() -> dict:
    """A day plan where every field runs past its budget.

    Nothing here is shortened to fit, which is the point: the renderer clamps
    and the layout holds, or one of these tests says which one gave way.
    """
    offerings = [
        {
            "label": _over_length(BUDGET_OFFERING_LABEL, f"Fictional offering {index}"),
            "location": _over_length(BUDGET_OFFERING_LOCATION, f"Room {index}00 annex"),
        }
        for index in range(1, MAX_OFFERINGS + 1)
    ]
    return {
        "format": DAY_PLAN_FORMAT,
        "date": FROZEN_DATE.isoformat(),
        "school_wide": {
            "events": [
                {
                    "label": _over_length(
                        BUDGET_OFFERING_LABEL, f"Invented event {index}"
                    ),
                    "when": "Thursday",
                }
                for index in range(1, 7)
            ],
            "bobcat_hour_offerings": offerings,
        },
        "teacher": {
            "bobcat_hour_here": {
                "label": _over_length(BUDGET_OFFERING_LABEL, "Retakes in this room"),
                "location": _over_length(BUDGET_OFFERING_LOCATION, "Room 108 back"),
            },
        },
        "sections": {
            block_id: {
                "learning_goal": _over_length(
                    BUDGET_LEARNING_GOAL, "Explain how a claim earns its evidence"
                ),
                "success_criteria": [
                    _over_length(BUDGET_SUCCESS_CRITERION, f"Name the reason {index}")
                    for index in range(1, 5)
                ],
                "work": [
                    {
                        "name": _over_length(
                            BUDGET_WORK_NAME, f"Draft paragraph {index}"
                        ),
                        "detail": _over_length(
                            BUDGET_WORK_DETAIL, f"Hand it in on paper {index}"
                        ),
                    }
                    for index in range(1, 5)
                ],
                "banner": [
                    _over_length(BUDGET_LEARNING_GOAL, "A few people still owe this"),
                ],
            }
            for block_id in ("p1", "p2", "p3", "p5", "p6", "p7")
        },
    }


# ------------------------------------------------------------------- the server


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _write_workspace(root: Path) -> tuple[Path, Path]:
    """Lay out an isolated machine config and workspace. Returns both roots."""
    local_app_data = root / "LocalAppData"
    workspace = root / "workspace" / "CanvasExpert"

    schedules = workspace / "Library" / "Bell Schedules"
    day_plans = workspace / "_System" / "Glass" / "day-plans"
    schedules.mkdir(parents=True, exist_ok=True)
    day_plans.mkdir(parents=True, exist_ok=True)

    (schedules / "fictional-bells.json").write_text(
        json.dumps(_schedule_data(), indent=2), encoding="utf-8"
    )
    (day_plans / f"{FROZEN_DATE.isoformat()}.json").write_text(
        json.dumps(_plan_data(), indent=2), encoding="utf-8"
    )

    # Written before the server starts, and this matters: reading machine config
    # migrates a legacy in-app-folder config.json into place when the new path
    # is missing, and the repo carries such a file. An existing file short
    # circuits that, so no real machine config is ever copied here.
    config_dir = local_app_data / "CanvasExpert"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.json").write_text(
        json.dumps(
            {
                "canvas_base": "https://canvas.example.test",
                "workspace_path": str(workspace),
                "saved_courses": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return local_app_data, workspace


@pytest.fixture(scope="session")
def glass_server(tmp_path_factory) -> str:
    """A real Glass server on a free port, reading a temp workspace.

    Session scoped because starting one is slow and every test wants the same
    page. Torn down through a `finally` so a failure part way through does not
    leave a server listening.
    """
    root = tmp_path_factory.mktemp("glass-geometry")
    local_app_data, _ = _write_workspace(root)

    port = _free_port()
    env = dict(os.environ)
    env["LOCALAPPDATA"] = str(local_app_data)
    env.pop("OneDrive", None)
    env.pop("OneDriveCommercial", None)

    process = subprocess.Popen(
        [
            sys.executable, "-c", _SERVER_BOOTSTRAP,
            str(REPO_ROOT), str(API_DIR), str(port),
        ],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_until_serving(process, base_url)
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=15)


def _wait_until_serving(process: subprocess.Popen, base_url: str) -> None:
    """Poll a gate-free URL until the server answers, or give up and say why."""
    deadline = time.monotonic() + 90.0
    # /static is on the onboarding gate's allowlist, so a 200 here means the
    # app is up without saying anything about whether /glass is reachable.
    probe_url = f"{base_url}/static/pages/glass.css"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout else ""
            raise AssertionError(
                f"the Glass test server exited with code {process.returncode} "
                f"before it started serving:\n{output[-4000:]}"
            )
        try:
            with urllib.request.urlopen(probe_url, timeout=2) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, OSError):
            time.sleep(0.25)
    raise AssertionError(f"the Glass test server never answered on {base_url}")


@pytest.fixture(scope="session")
def glass_chromium() -> str:
    """Where this machine's Chromium is, or a clear skip when there is not one.

    Session scoped for a reason beyond speed. Playwright finds its downloaded
    browsers under `%LOCALAPPDATA%`, and the suite's isolation fixture points
    `LOCALAPPDATA` at an empty temp directory on purpose, so a lookup done from
    inside a test finds nothing. Session-scoped fixtures are set up before
    function-scoped ones, so this one asks while the real value is still in
    place and hands the answer along. The isolation fixture stays exactly as it
    is, and every later browser launch is told the path outright.
    """
    with sync_api.sync_playwright() as play:
        executable = play.chromium.executable_path
    if not executable or not os.path.exists(executable):
        pytest.skip(
            "Playwright's Chromium is not installed. Enable these tests with: "
            "py -m playwright install chromium"
        )
    return str(executable)


@pytest.fixture(params=VIEWPORTS, ids=lambda size: f"{size[0]}x{size[1]}")
def glass_page(request, glass_server, glass_chromium):
    """One page showing the frozen instant, at each 16:10 viewport in turn.

    Playwright is opened and closed inside a single test rather than held for
    the session on purpose. `sync_playwright()` keeps an asyncio loop running
    for as long as its context is open, and a loop left running underneath the
    rest of the suite breaks any later test that calls `asyncio.run()`. A
    browser launch costs a fraction of a second, so the boring scope is also
    the cheap one.

    The sanity check before yielding is deliberate. Every measurement in this
    module would pass on an empty page, so this fails loudly if the workspace
    seam ever stops reaching the server and Glass renders a day with nothing
    in it.
    """
    width, height = request.param
    with sync_api.sync_playwright() as play:
        try:
            browser = play.chromium.launch(executable_path=glass_chromium)
        except sync_api.Error as err:
            pytest.skip(
                f"Playwright could not start Chromium ({err}). Enable these "
                f"tests with: py -m playwright install chromium"
            )
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(f"{glass_server}/glass?at={FROZEN_AT}", wait_until="load")
            page.wait_for_selector("#glass-tray")
            rendered = page.evaluate(_MEASURE_TEXT)
            assert rendered["nowLabel"] == "1st Period", rendered
            assert rendered["goal"], "the focus slot rendered no learning goal"
            assert rendered["bobcatItems"] == MAX_OFFERINGS + 1, rendered
            yield page
        finally:
            browser.close()


# --------------------------------------------------------------- AC 6, clamping


def test_no_frame_container_hides_overflow(glass_page):
    """AC 6: over-length content clamps, and the layout frame still fits."""
    measured = glass_page.evaluate(_MEASURE_FRAME, list(FRAME_SELECTORS))
    assert measured["boxes"], "no frame containers were found, check the selectors"

    for box in measured["boxes"]:
        where = f"{box['selector']}[{box['index']}]"
        if box["id"]:
            where = f"{where} (#{box['id']})"
        assert box["scrollWidth"] <= box["clientWidth"] + TOLERANCE_PX, (
            f"{where} hides {box['scrollWidth'] - box['clientWidth']}px of width "
            f"({box['scrollWidth']} inside {box['clientWidth']})"
        )
        assert box["scrollHeight"] <= box["clientHeight"] + TOLERANCE_PX, (
            f"{where} hides {box['scrollHeight'] - box['clientHeight']}px of "
            f"height ({box['scrollHeight']} inside {box['clientHeight']})"
        )

    print(
        f"frame: {len(measured['boxes'])} containers measured at "
        f"{measured['innerWidth']}x{measured['innerHeight']}"
    )
    assert measured["docScrollWidth"] <= measured["innerWidth"] + TOLERANCE_PX, (
        f"the document scrolls sideways: {measured['docScrollWidth']} wide in a "
        f"{measured['innerWidth']}px viewport"
    )
    assert measured["docScrollHeight"] <= measured["innerHeight"] + TOLERANCE_PX, (
        f"the document scrolls vertically: {measured['docScrollHeight']} tall in "
        f"a {measured['innerHeight']}px viewport"
    )


def test_bobcat_pane_fits_at_maximum_offering_count(glass_page):
    """AC 6: the pane that holds its ground, with more offerings than it can show.

    The Bobcat Hour pane sits on an intrinsic grid row on purpose: the brief has
    events shed items first and this pane hold its ground, which makes it the one
    pane whose content could push the layout. Two things get measured. The pane
    stays inside the right rail no matter how long the offering list runs, and it
    still shows a realistic slate in full. The second half is what keeps this
    honest: past its capacity the pane clips the rest of the list silently, so a
    containment check on its own would pass at any count and prove nothing.
    """
    measured = glass_page.evaluate(_MEASURE_BOBCAT)
    assert measured["items"] == MAX_OFFERINGS + 1, measured

    print(
        f"bobcat: {measured['items']} items rendered, {measured['fullyVisible']} "
        f"fully visible, pane {measured['paneHeight']:.1f}px tall inside a rail "
        f"of {measured['panesClientHeight']:.1f}px"
    )
    assert measured["paneTop"] >= measured["panesTop"] - TOLERANCE_PX, measured
    assert measured["paneBottom"] <= measured["panesBottom"] + TOLERANCE_PX, (
        f"the Bobcat Hour pane at {measured['items']} items runs "
        f"{measured['paneBottom'] - measured['panesBottom']:.1f}px past the "
        f"bottom of the right rail"
    )
    assert (
        measured["panesScrollHeight"] <= measured["panesClientHeight"] + TOLERANCE_PX
    ), (
        f"the right rail hides "
        f"{measured['panesScrollHeight'] - measured['panesClientHeight']:.1f}px of "
        f"content at {measured['items']} Bobcat Hour items"
    )
    assert measured["fullyVisible"] >= VISIBLE_ITEM_FLOOR, (
        f"the Bobcat Hour pane shows only {measured['fullyVisible']} items in "
        f"full, and a realistic slate is {VISIBLE_ITEM_FLOOR}"
    )


def test_rendered_text_stays_inside_its_character_budget(glass_page):
    """AC 6, at the character level: the renderer clamps rather than reflows."""
    rendered = glass_page.evaluate(_MEASURE_TEXT)

    def within(label: str, value: str, budget: int) -> None:
        assert len(value) <= budget, (
            f"{label} rendered {len(value)} characters against a budget of "
            f"{budget}: {value!r}"
        )

    within("the learning goal", rendered["goal"], BUDGET_LEARNING_GOAL)
    assert rendered["criteria"], rendered
    for index, criterion in enumerate(rendered["criteria"], start=1):
        within(f"success criterion {index}", criterion, BUDGET_SUCCESS_CRITERION)
    assert rendered["workNames"], rendered
    for index, name in enumerate(rendered["workNames"], start=1):
        within(f"work item {index} name", name, BUDGET_WORK_NAME)
    for index, detail in enumerate(rendered["workDetails"], start=1):
        within(f"work item {index} detail", detail, BUDGET_WORK_DETAIL)
    assert len(rendered["offeringNames"]) == MAX_OFFERINGS, rendered
    for index, label in enumerate(rendered["offeringNames"], start=1):
        within(f"offering {index} label", label, BUDGET_OFFERING_LABEL)
    for index, location in enumerate(rendered["offeringLocations"], start=1):
        within(f"offering {index} location", location, BUDGET_OFFERING_LOCATION)
    within("this room's own offering", rendered["hereName"], BUDGET_OFFERING_LABEL)


# ------------------------------------------------------------------- AC 7, reach


def _assert_touch_targets_reachable(page, state: str) -> dict:
    measured = page.evaluate(_MEASURE_TOUCH)
    targets = measured["targets"]
    assert targets, (
        f"no visible touch targets were found in the {state} state, so nothing "
        f"was measured"
    )

    width = measured["innerWidth"]
    height = measured["innerHeight"]
    reach_line = height * BOTTOM_THIRD
    width_floor = width * MIN_TOUCH_WIDTH_FRACTION

    for target in targets:
        assert target["top"] >= reach_line - TOLERANCE_PX, (
            f"{state}: '{target['label']}' starts at y={target['top']:.1f}, above "
            f"the bottom third of a {height}px screen (which begins at "
            f"{reach_line:.1f})"
        )
        assert target["width"] >= width_floor - TOLERANCE_PX, (
            f"{state}: '{target['label']}' is {target['width']:.1f}px wide, under "
            f"9% of a {width}px screen ({width_floor:.1f}px)"
        )
        assert target["bottom"] <= height + TOLERANCE_PX, (
            f"{state}: '{target['label']}' ends at y={target['bottom']:.1f}, past "
            f"the bottom of a {height}px screen"
        )

    highest = min(target["top"] for target in targets)
    narrowest = min(target["width"] for target in targets)
    print(
        f"touch {state} at {width}x{height}: {len(targets)} targets, highest top "
        f"{highest:.1f} ({highest / height:.3f} of height), narrowest "
        f"{narrowest:.1f}px ({narrowest / width:.4f} of width)"
    )
    return measured


def test_every_touch_target_is_low_and_wide_enough_at_rest(glass_page):
    """AC 7, tray at rest: the duration presets."""
    measured = _assert_touch_targets_reachable(glass_page, "rest")
    # Both tray states ship in the DOM, so the visible set is a subset. A test
    # that measured everything would be measuring a hidden state's zero boxes.
    assert len(measured["targets"]) < measured["total"], measured


def test_every_touch_target_is_low_and_wide_enough_while_running(glass_page):
    """AC 7, tray while running: pause, resume, plus one minute, reset.

    Measured twice, because arming reset swaps in longer wording and a wider
    button is the one way this row could grow past the tray.
    """
    glass_page.click('[data-glass-preset="10"]')
    glass_page.wait_for_selector("#glass-tray-running:not([hidden])")
    _assert_touch_targets_reachable(glass_page, "running")

    glass_page.click("#glass-timer-reset")
    glass_page.wait_for_selector('#glass-timer-reset[data-glass-armed="yes"]')
    _assert_touch_targets_reachable(glass_page, "running, reset armed")
    row = glass_page.evaluate(_MEASURE_FRAME, [".glass-tray__row", "#glass-tray"])
    for box in row["boxes"]:
        assert box["scrollWidth"] <= box["clientWidth"] + TOLERANCE_PX, box
        assert box["scrollHeight"] <= box["clientHeight"] + TOLERANCE_PX, box


# ------------------------------------------------------------ AC 9, a fixed tray


def test_tray_height_is_identical_through_every_timer_state(glass_page):
    """AC 9: starting, pausing, and resetting a timer move nothing.

    The tray's height is the criterion, and the focus slot's top is the harm it
    guards against, so both are measured in every state.
    """
    states: list[tuple[str, dict]] = []

    rest = glass_page.evaluate(_MEASURE_TRAY)
    assert rest["restVisible"] and not rest["runningVisible"], rest
    states.append(("rest", rest))

    glass_page.click('[data-glass-preset="10"]')
    glass_page.wait_for_selector("#glass-tray-running:not([hidden])")
    running = glass_page.evaluate(_MEASURE_TRAY)
    assert running["runningVisible"] and not running["restVisible"], running
    states.append(("running", running))

    glass_page.click('[data-glass-timer="pause"]')
    states.append(("paused", glass_page.evaluate(_MEASURE_TRAY)))

    # Reset asks a second time before it acts, so the first tap only arms it.
    # The armed button carries longer text, which is exactly the kind of change
    # that could grow a tray, so the armed state is measured too.
    glass_page.click("#glass-timer-reset")
    glass_page.wait_for_selector('#glass-timer-reset[data-glass-armed="yes"]')
    states.append(("reset armed", glass_page.evaluate(_MEASURE_TRAY)))

    glass_page.click("#glass-timer-reset")
    glass_page.wait_for_selector("#glass-tray-rest:not([hidden])")
    after_reset = glass_page.evaluate(_MEASURE_TRAY)
    assert after_reset["restVisible"] and not after_reset["runningVisible"], after_reset
    states.append(("after reset", after_reset))

    print(
        "tray: "
        + ", ".join(
            f"{name} {snapshot['trayHeight']:.2f}px (top {snapshot['trayTop']:.2f}, "
            f"focus top {snapshot['focusTop']:.2f})"
            for name, snapshot in states
        )
    )

    baseline_name, baseline = states[0]
    for name, snapshot in states[1:]:
        assert abs(snapshot["trayHeight"] - baseline["trayHeight"]) <= TOLERANCE_PX, (
            f"the tray is {snapshot['trayHeight']:.2f}px tall {name} and "
            f"{baseline['trayHeight']:.2f}px tall at {baseline_name}"
        )
        assert abs(snapshot["trayTop"] - baseline["trayTop"]) <= TOLERANCE_PX, (
            f"the tray starts at y={snapshot['trayTop']:.2f} {name} and "
            f"y={baseline['trayTop']:.2f} at {baseline_name}"
        )
        assert abs(snapshot["focusTop"] - baseline["focusTop"]) <= TOLERANCE_PX, (
            f"the focus slot starts at y={snapshot['focusTop']:.2f} {name} and "
            f"y={baseline['focusTop']:.2f} at {baseline_name}, so a timer moved "
            f"the content above the tray"
        )
