"""Required real-Edge isolation tests for the local Glass display."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import base64
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

from api.glass import panes

ROOT = Path(__file__).resolve().parents[3]
HOSTILE_FROZEN = "2099-09-14T08:35:00"
SAFE_FROZEN = "2099-09-15T08:35:00"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def _port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _pane(name, title, schema, example, html, script=""):
    return {"manifest": {"format": panes.PANE_FORMAT, "id": name, "title": title,
            "description": "Fictional fixture pane.", "data_schema": schema, "example_data": example},
            "pane_html": html, "pane_css": "body{font:16px sans-serif}button{padding:.5rem}",
            "pane_js": script, "assets": []}


def _approve_pane(payload, root):
    draft = panes.save_pane_draft(payload, root=str(root))
    assert draft["ok"], draft
    approved = panes.approve_pane(draft["draft_id"], draft["digest"], str(root))
    assert approved["ok"], approved
    return approved


def _instance(instance_id, approved, data, column, row, width, height):
    return {"instance_id": instance_id, "pane_id": approved["pane_id"],
            "pane_revision": approved["pane_revision"], "data": data,
            "column": column, "row": row, "width": width, "height": height}


def _approve_scene(scene, root):
    draft = panes.save_scene_draft(scene, root=str(root))
    assert draft["ok"], draft
    approved = panes.approve_scene(draft["draft_id"], draft["digest"], str(root))
    assert approved["ok"], approved


def _workspace(root):
    glass = root / "Library" / "Glass"
    glass.mkdir(parents=True)
    glass.joinpath("bells.json").write_text(json.dumps({
        "format": "canvasexpert.bell_schedule/1", "day_types": {"d": {"label": "Fictional day", "blocks": [
            {"id": "p1", "kind": "class", "label": "One", "start": "08:30", "end": "09:00"},
            {"id": "p2", "kind": "class", "label": "Two", "start": "09:00", "end": "09:30"},
        ]}}, "weekday_default": {str(day): "d" for day in range(7)}}))
    lesson_data = {"lesson": "Fraction Lab", "objective": "Compare equivalent fractions.</script><script>document.body.dataset.contextInjection='ran'</script>"}
    upcoming_data = {"items": [{"title": "Notebook check", "due": "Friday"}]}
    touch_data = {"prompt": "Tap when your table is ready."}
    lesson = _approve_pane(_pane("lesson-focus", "Lesson focus",
        {"type": "object", "additionalProperties": False, "required": ["lesson", "objective"], "properties": {"lesson": {"type": "string"}, "objective": {"type": "string"}}}, lesson_data,
        "<section><h1 id='lesson-title'></h1><p id='lesson-objective'></p></section>",
        "var d=window.glassContext.data;document.querySelector('#lesson-title').textContent=d.lesson;document.querySelector('#lesson-objective').textContent=d.objective;"), root)
    upcoming = _approve_pane(_pane("upcoming-work", "Upcoming work",
        {"type": "object", "additionalProperties": False, "required": ["items"], "properties": {"items": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["title", "due"], "properties": {"title": {"type": "string"}, "due": {"type": "string"}}}}}}, upcoming_data,
        "<section><h2>Upcoming</h2><ul id='upcoming-items'></ul></section>",
        "var d=window.glassContext.data;document.querySelector('#upcoming-items').replaceChildren(...d.items.map(function(i){var e=document.createElement('li');e.textContent=i.title+' — '+i.due;return e}));"), root)
    touch = _approve_pane(_pane("touch-instructions", "Touch instructions",
        {"type": "object", "additionalProperties": False, "required": ["prompt"], "properties": {"prompt": {"type": "string"}}}, touch_data,
        "<section><p id='touch-prompt'></p><button id='touch'>Ready</button></section>",
        "document.querySelector('#touch-prompt').textContent=window.glassContext.data.prompt;document.querySelector('#touch').onclick=function(){document.body.dataset.touch='yes'};"), root)
    hostile_script = """
var join=function(){return Array.prototype.join.call(arguments,'')};
var target=join('ht','tps',':','//','invalid','.test');
var attempt=function(name,work){try{work()}catch(e){}finally{document.body.dataset[name]='1'}};
clearInterval(window._glassHeartbeat);
attempt('parent',function(){window[join('par','ent')].document.body.dataset.pwn='x'});
attempt('storage',function(){window[join('local','Storage')].setItem('x','x')});
attempt(join('fe','tch'),function(){window[join('fe','tch')](target).catch(function(){})});
attempt('xhr',function(){var C=window[join('XML','Http','Request')],x=new C();x.open('GET',target);x.send()});
attempt('socket',function(){new window[join('Web','Socket')](join('ws','s',':','//','invalid','.test'))});
attempt(join('event','source'),function(){new window[join('Event','Source')](target)});
attempt('form',function(){var f=document.createElement(join('fo','rm'));f.action=target;document.body.append(f);f.submit()});
attempt('popup',function(){window[join('op','en')](target)});
attempt('topnav',function(){window[join('to','p')][join('loc','ation')]=target});
"""
    hostile = _approve_pane(_pane("hostile-sandbox", "Hostile sandbox fixture",
        {"type": "object", "additionalProperties": False}, {},
        "<p id='hostile-status'>Attempting isolated capabilities.</p>", hostile_script), root)
    safe_default = [_instance("lesson-focus", lesson, lesson_data, 1, 1, 6, 4),
                    _instance("upcoming-work", upcoming, upcoming_data, 7, 1, 6, 4),
                    _instance("touch-instructions", touch, touch_data, 1, 5, 12, 4)]
    for scene_day in (SAFE_FROZEN[:10], date.today().isoformat()):
        _approve_scene({"format": panes.SCENE_FORMAT, "date": scene_day, "title": "Fictional safe reference", "default": safe_default,
                        "blocks": {"p2": [_instance("p2-upcoming-work", upcoming, upcoming_data, 1, 1, 12, 8)]}}, root)
    _approve_scene({"format": panes.SCENE_FORMAT, "date": HOSTILE_FROZEN[:10], "title": "Fictional sandbox test", "default": [
        _instance("lesson-focus", lesson, lesson_data, 1, 1, 6, 3),
        _instance("upcoming-work", upcoming, upcoming_data, 7, 1, 6, 3),
        _instance("touch-instructions", touch, touch_data, 1, 4, 6, 5),
        _instance("hostile-sandbox", hostile, {}, 7, 4, 6, 5)], "blocks": {}}, root)
    pending_pane = _pane("pending-notice", "Pending notice",
        {"type": "object", "additionalProperties": False, "required": ["announcement"], "properties": {"announcement": {"type": "string"}}},
        {"announcement": "Bring a pencil to the fictional lab."},
        "<p id='pending-notice'></p>", "document.querySelector('#pending-notice').textContent=window.glassContext.data.announcement;")
    pending_pane["assets"] = [{"name": "fictional-dot.gif", "media_type": "image/gif",
        "data_base64": base64.b64encode(b"GIF89a").decode()}]
    pending_pane_draft = panes.save_pane_draft(pending_pane, root=str(root))
    assert pending_pane_draft["ok"], pending_pane_draft
    pending_scene_draft = panes.save_scene_draft({"format": panes.SCENE_FORMAT, "date": "2099-09-16",
        "title": "Pending fictional review scene", "default": safe_default,
        "blocks": {"p2": [_instance("p2-upcoming-work", upcoming, upcoming_data, 1, 1, 12, 8)]}}, root=str(root))
    assert pending_scene_draft["ok"], pending_scene_draft
    return {"pending_pane": pending_pane_draft, "pending_scene": pending_scene_draft}


def _server(root, tmp):
    local = tmp / "local"; (local / "CanvasExpert").mkdir(parents=True)
    (local / "CanvasExpert" / "config.json").write_text(json.dumps({"workspace_path": str(root), "canvas_base": "https://canvas.example.test", "saved_courses": []}))
    port = _port(); env = dict(os.environ); env["LOCALAPPDATA"] = str(local)
    process = subprocess.Popen([sys.executable, "-c", "import sys;sys.path.insert(0,sys.argv[1]);import uvicorn;uvicorn.run('api.webui.server:app',host='127.0.0.1',port=int(sys.argv[2]),lifespan='off',log_level='warning')", str(ROOT), str(port)], cwd=str(ROOT), env=env)
    url = f"http://127.0.0.1:{port}"
    for _ in range(80):
        try:
            if urllib.request.urlopen(url + "/glass", timeout=1).status == 200: return process, url
        except OSError: time.sleep(.1)
    raise AssertionError("server")


def _frame(page, instance_id):
    return page.locator(f"iframe[data-instance='{instance_id}']").content_frame


def test_real_edge_sandbox_watchdog_context_and_viewports(tmp_path):
    root = tmp_path / "ws"; _workspace(root); process, url = _server(root, tmp_path)
    try:
        assert os.path.exists(EDGE), "required Edge unavailable"
        with sync_playwright() as play:
            browser = play.chromium.launch(executable_path=EDGE)
            for width, height in ((1280, 720), (1920, 1080), (1280, 800), (1920, 1200)):
                page = browser.new_page(viewport={"width": width, "height": height}); escaped = []
                page.on("requestfinished", lambda request: escaped.append(request.url)); page.goto(url + "/glass/display?at=" + HOSTILE_FROZEN)
                page.wait_for_selector("iframe[data-instance='hostile-sandbox']")
                hostile = _frame(page, "hostile-sandbox"); hostile.locator("body").wait_for(); page.wait_for_timeout(250)
                markers = hostile.locator("body").evaluate("body=>Object.assign({},body.dataset)")
                assert all(markers.get(name) == "1" for name in ("parent", "storage", "fetch", "xhr", "socket", "eventsource", "form", "popup", "topnav"))
                lesson = _frame(page, "lesson-focus")
                assert lesson.locator("body").evaluate("body=>window.glassContext") == {"type": "glass:context/1", "instance_id": "lesson-focus", "scene_date": "2099-09-14", "data": {"lesson": "Fraction Lab", "objective": "Compare equivalent fractions.</script><script>document.body.dataset.contextInjection='ran'</script>"}, "local_time": HOSTILE_FROZEN, "current_block": {"id": "p1", "start": "08:30", "end": "09:00", "label": "One"}}
                assert lesson.locator("body").evaluate("body=>body.dataset.contextInjection") is None
                page.wait_for_timeout(4200)
                assert page.evaluate("document.documentElement.scrollWidth===innerWidth&&document.documentElement.scrollHeight===innerHeight")
                assert page.locator(".glass-cell[data-instance='hostile-sandbox'] .glass-pane-failure").count() == 1
                assert page.locator(".glass-rail").is_visible()
                assert page.locator("#glass-status").inner_text() == "Some content is unavailable."
                for instance_id in ("lesson-focus", "upcoming-work", "touch-instructions"):
                    assert page.locator(f".glass-cell[data-instance='{instance_id}'] iframe").count() == 1
                touch = _frame(page, "touch-instructions"); touch.locator("#touch").click()
                assert touch.locator("body").evaluate("body=>body.dataset.touch") == "yes"
                assert page.url == url + "/glass/display?at=" + HOSTILE_FROZEN and page.evaluate("document.body.dataset.pwn") is None
                assert not [request for request in escaped if "invalid.test" in request or "/api/" in request]
                page.reload(); _frame(page, "touch-instructions").locator("body").wait_for()
                assert _frame(page, "touch-instructions").locator("body").evaluate("body=>body.dataset.touch||''") == ""; page.close()
            browser.close()
    finally:
        process.terminate(); process.wait(timeout=15)


def test_unfrozen_local_block_transition_and_frozen_clock(tmp_path):
    root = tmp_path / "ws"; _workspace(root); process, url = _server(root, tmp_path)
    shim = """(()=>{const R=Date;let n=new R('2099-09-15T08:35:00').valueOf();class D extends R{constructor(...a){super(...(a.length?a:[n]))}static now(){return n}}window.Date=D;window.__glassAdvance=v=>n=new R(v).valueOf()})()"""
    try:
        with sync_playwright() as play:
            browser = play.chromium.launch(executable_path=EDGE); page = browser.new_page(); page.add_init_script(shim); page.goto(url + "/glass/display")
            page.wait_for_selector("iframe[data-instance='lesson-focus']"); host = json.loads(page.locator("#glass-data").inner_text())
            assert [block["id"] for block in host["blocks"]] == ["p1", "p2"] and page.locator("#glass-block").inner_text() == "One"
            assert page.locator(".glass-cell[data-layout='default']:not([hidden])").count() == 3
            requests = []; page.on("request", lambda request: requests.append(request.url)); page.evaluate("__glassAdvance('2099-09-15T09:05:00')"); page.wait_for_timeout(1200)
            assert page.locator(".glass-cell[data-layout='p2']:not([hidden])").count() == 1 and page.locator(".glass-cell[data-layout='default']:not([hidden])").count() == 0 and page.locator("#glass-block").inner_text() == "Two" and not requests
            p2 = _frame(page, "p2-upcoming-work"); p2.locator("body").wait_for()
            p2_context = p2.locator("body").evaluate("body=>window.glassContext")
            assert p2_context == {"type": "glass:context/1", "instance_id": "p2-upcoming-work", "scene_date": date.today().isoformat(),
                                  "data": {"items": [{"title": "Notebook check", "due": "Friday"}]}, "local_time": "2099-09-15T09:05:00",
                                  "current_block": {"id": "p2", "start": "09:00", "end": "09:30", "label": "Two"}}
            frozen = browser.new_page(); frozen.add_init_script(shim); frozen.goto(url + "/glass/display?at=" + SAFE_FROZEN); frozen.wait_for_selector("iframe[data-instance='lesson-focus']")
            before = frozen.locator("#glass-clock").inner_text(); frozen.evaluate("__glassAdvance('2099-09-15T09:05:00')"); frozen.wait_for_timeout(1200)
            assert frozen.locator(".glass-cell[data-layout='default']:not([hidden])").count() == 3 and frozen.locator("#glass-clock").inner_text() == before
            browser.close()
    finally:
        process.terminate(); process.wait(timeout=15)


def test_real_edge_authored_runtime_error_isolated_to_its_pane(tmp_path):
    root = tmp_path / "ws"; _workspace(root)
    healthy = _approve_pane(_pane("healthy-pane", "Healthy pane", {"type": "object"}, {}, "<p id='healthy'>Still live</p>"), root)
    broken = _approve_pane(_pane("broken-pane", "Broken pane", {"type": "object"}, {}, "<p>Broken</p>", "throw new Error('fictional authored runtime failure');"), root)
    _approve_scene({"format": panes.SCENE_FORMAT, "date": "2099-09-17", "title": "Fictional error isolation", "blocks": {}, "default": [
        _instance("healthy-pane", healthy, {}, 1, 1, 6, 8), _instance("broken-pane", broken, {}, 7, 1, 6, 8),
    ]}, root)
    process, url = _server(root, tmp_path)
    try:
        with sync_playwright() as play:
            browser = play.chromium.launch(executable_path=EDGE); page = browser.new_page()
            page.goto(url + "/glass/display?at=2099-09-17T08:45:00")
            page.locator(".glass-cell[data-instance='broken-pane'] .glass-pane-failure").wait_for(timeout=6000)
            assert page.locator(".glass-rail").is_visible()
            assert _frame(page, "healthy-pane").locator("#healthy").inner_text() == "Still live"
            assert page.locator(".glass-cell[data-instance='broken-pane'] .glass-pane-failure").inner_text() == "Pane unavailable."
            assert page.locator("#glass-status").inner_text() == "Some content is unavailable."
            assert "fictional authored runtime failure" not in page.locator("body").inner_text()
            browser.close()
    finally:
        process.terminate(); process.wait(timeout=15)


def _no_horizontal_overflow(page):
    return page.evaluate("document.documentElement.scrollWidth<=window.innerWidth")


def _no_display_overflow(page):
    return page.evaluate("document.documentElement.scrollWidth<=window.innerWidth&&document.documentElement.scrollHeight<=window.innerHeight")


def test_real_edge_normal_review_preview_and_display_matrix(tmp_path):
    root = tmp_path / "ws"
    drafts = _workspace(root)
    process, url = _server(root, tmp_path / "populated")
    empty_process, empty_url = _server(tmp_path / "empty-ws", tmp_path / "empty")
    try:
        assert os.path.exists(EDGE), "required Edge unavailable"
        with sync_playwright() as play:
            browser = play.chromium.launch(executable_path=EDGE)
            for width, height in ((1280, 720), (1920, 1080), (1280, 800), (1920, 1200)):
                page = browser.new_page(viewport={"width": width, "height": height})
                errors = []
                page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
                page.on("pageerror", lambda error: errors.append(str(error)))

                page.goto(url + "/glass")
                page.wait_for_selector("#glass-review-root")
                assert page.locator("#glass-review-root").count() == 1
                assert page.locator("script[src*='/static/glass/review.js']").count() == 1
                assert page.locator("script[src*='/static/app_context.js']").count() == 1
                assert page.evaluate("typeof window.ceToast") == "function"
                assert _no_horizontal_overflow(page)
                pane_card = page.locator("iframe[title='Pane preview']").locator("xpath=..")
                scene_card = page.locator("iframe[title='Scene preview']").locator("xpath=..")
                assert pane_card.locator("pre").inner_text() == json.dumps(
                    {"announcement": "Bring a pencil to the fictional lab."}, indent=2
                )
                assert "fictional-dot.gif" in pane_card.locator("ul").last.inner_text()
                assert pane_card.locator("iframe[title='Pane preview']").count() == 1
                assert scene_card.locator("iframe[title='Scene preview']").count() == 1
                pane_preview = pane_card.locator("iframe[title='Pane preview']")
                pane_card.locator("[data-glass-aspect='16:10']").click()
                assert pane_preview.evaluate("frame=>frame.style.aspectRatio") == "16 / 10"
                assert pane_card.locator("[data-glass-aspect='16:10']").get_attribute("aria-pressed") == "true"
                assert pane_card.locator("[data-glass-aspect='16:9']").get_attribute("aria-pressed") == "false"
                pane_card.locator("[data-glass-aspect='16:9']").click()
                assert pane_preview.evaluate("frame=>frame.style.aspectRatio") == "16 / 9"
                assert pane_card.locator("[data-glass-aspect='16:9']").get_attribute("aria-pressed") == "true"
                assert pane_card.locator("[data-glass-aspect='16:10']").get_attribute("aria-pressed") == "false"

                selector = scene_card.locator("select[data-glass-layout]")
                scene_preview = scene_card.locator("iframe[title='Scene preview']")
                assert selector.locator("option").all_text_contents() == ["default", "p2"]
                for layout, visible_count in (("default", 3), ("p2", 1)):
                    selector.select_option(layout)
                    expected_suffix = f"/glass/preview/{drafts['pending_scene']['draft_id']}?layout={layout}"
                    page.wait_for_function("spec=>{const frame=document.querySelector(\"iframe[title='Scene preview']\"),doc=frame.contentWindow.document,digest=doc.getElementById('glass-preview-digest');return frame.contentWindow.location.href.endsWith(spec.suffix)&&digest&&digest.textContent===spec.digest&&doc.querySelectorAll('.glass-cell:not([hidden])').length===spec.visible}", arg={"suffix": expected_suffix, "digest": drafts["pending_scene"]["digest"], "visible": visible_count})
                    assert scene_preview.get_attribute("src").endswith(expected_suffix)
                assert not errors, "\n".join(errors)

                page.goto(url + f"/glass/preview/{drafts['pending_pane']['draft_id']}")
                page.wait_for_selector("#glass-preview-digest")
                assert page.locator("#glass-preview-digest").inner_text() == drafts["pending_pane"]["digest"]
                assert page.locator("script[src*='/static/glass/display.js']").count() == 1
                assert page.locator("#glass-data").count() == 1
                assert page.locator("iframe.glass-frame[sandbox='allow-scripts']").count() == 1
                assert _no_display_overflow(page)

                page.goto(url + f"/glass/preview/{drafts['pending_scene']['draft_id']}?layout=default")
                page.wait_for_selector("#glass-preview-digest")
                assert page.locator("#glass-preview-digest").inner_text() == drafts["pending_scene"]["digest"]
                assert page.locator("iframe.glass-frame[sandbox='allow-scripts']").count() == 4
                assert page.locator(".glass-cell[data-layout='default']:not([hidden]) iframe.glass-frame").count() == 3
                assert page.locator("script[src*='/static/glass/display.js']").count() == 1
                assert page.locator("#glass-data").count() == 1
                assert _no_display_overflow(page)

                page.goto(empty_url + "/glass/display?at=" + SAFE_FROZEN)
                page.wait_for_selector("#glass-empty")
                assert page.locator(".glass-rail").count() == 1
                assert page.locator("#glass-empty").inner_text() == "No approved scene for today."
                assert page.locator("#glass-status").inner_text() == "No approved scene for today."
                assert page.locator("#glass-data").count() == 1
                assert page.locator("script[src*='/static/glass/display.js']").count() == 1
                assert _no_display_overflow(page)

                page.goto(url + "/glass/display?at=" + SAFE_FROZEN)
                page.wait_for_selector("iframe[data-instance='lesson-focus']")
                assert page.locator(".glass-rail").count() == 1
                assert page.locator("#glass-status").inner_text() == "Ready."
                assert page.locator("iframe[data-instance='lesson-focus']").count() == 1
                assert page.locator("iframe[data-instance='upcoming-work']").count() == 1
                assert page.locator("iframe[data-instance='touch-instructions']").count() == 1
                assert page.locator("#glass-data").count() == 1
                assert page.locator("script[src*='/static/glass/display.js']").count() == 1
                assert _no_display_overflow(page)
                assert not errors, "\n".join(errors)
                page.close()
            browser.close()
    finally:
        process.terminate(); process.wait(timeout=15)
        empty_process.terminate(); empty_process.wait(timeout=15)
