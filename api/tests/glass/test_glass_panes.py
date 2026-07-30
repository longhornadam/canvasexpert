"""Focused, synthetic validation and immutable-revision tests for Glass panes."""
import base64
import json
import re
from pathlib import Path

import pytest

from api.glass import panes
from api.webui.routes import glass as glass_routes


def _asset(name, media, data):
    return {"name": name, "media_type": media, "data_base64": base64.b64encode(data).decode()}


def _pane():
    return {"manifest": {"format": panes.PANE_FORMAT, "id": "instruction-pane", "title": "Instructions", "description": "Fictional", "data_schema": {"type": "object", "required": ["text"], "properties": {"text": {"type": "string"}}}, "example_data": {"text": "Read"}}, "pane_html": "<main>Read</main>", "pane_css": "", "pane_js": "", "assets": []}


@pytest.mark.parametrize("mutate", [
    lambda p: p["manifest"].__setitem__("extra", True),
    lambda p: p["manifest"].pop("title"),
    lambda p: p["manifest"].__setitem__("id", "Not kebab"),
    lambda p: p["manifest"].__setitem__("title", ""),
    lambda p: p["manifest"].__setitem__("data_schema", {"type": "nonsense"}),
    lambda p: p["manifest"].__setitem__("example_data", {}),
    lambda p: p.__setitem__("pane_html", ""),
    lambda p: p.__setitem__("pane_css", 1),
    lambda p: p.__setitem__("pane_js", "fetch('https://remote.example')"),
])
def test_manifest_and_source_rejections(mutate):
    value = _pane(); mutate(value); errors, _ = panes.validate_pane(value); assert errors


@pytest.mark.parametrize("field,value,valid", [
    ("pane_html", "<img src='asset:dot.gif'><a href='#local'>x</a><form action='data:text/plain,x'></form>", True),
    ("pane_html", "<img src='relative.png'>", False), ("pane_html", "<a href='/root'>x</a>", False),
    ("pane_html", "<img srcset='asset:one.png 1x, /root.png 2x'>", False),
    ("pane_html", "<form formaction='https://remote.example'>x</form>", False),
    ("pane_html", "<video poster='poster.png'></video>", False),
    ("pane_css", "@import url(asset:local.css);.x{background:url(data:image/png;base64,AA==)}", True),
    ("pane_css", "@import 'relative.css';", False), ("pane_css", ".x{background:url(../image.png)}", False),
])
def test_pane_url_bearing_sources_are_local_only(field, value, valid):
    payload = _pane(); payload[field] = value
    errors, _ = panes.validate_pane(payload)
    assert (not errors) is valid


@pytest.mark.parametrize("asset,valid", [
    (_asset("a.png", "image/png", b"\x89PNG\r\n\x1a\n"), True),
    (_asset("a.jpg", "image/jpeg", b"\xff\xd8\xffx"), True),
    (_asset("a.gif", "image/gif", b"GIF89a"), True),
    (_asset("a.webp", "image/webp", b"RIFF0000WEBP"), True),
    (_asset("a.woff", "font/woff", b"wOFF"), True),
    (_asset("a.woff2", "font/woff2", b"wOF2"), True),
    (_asset("../a.png", "image/png", b"\x89PNG\r\n\x1a\n"), False),
    (_asset("a.png", "text/plain", b"x"), False),
    ({"name": "a.png", "media_type": "image/png", "data_base64": "%%%"}, False),
    (_asset("a.png", "image/png", b"GIF89a"), False),
])
def test_asset_media_validation(asset, valid):
    value = _pane(); value["assets"] = [asset]; errors, _ = panes.validate_pane(value); assert (not errors) is valid


@pytest.mark.parametrize("body,valid", [
    (b"<svg xmlns='http://www.w3.org/2000/svg'><path d=''/></svg>", True),
    (b"<svg><script/></svg>", False), (b"<svg><foreignObject/></svg>", False),
    (b"<svg onload='x'/>", False), (b"<svg><use href='https://x'/></svg>", False),
    (b"<!DOCTYPE svg><svg/>", False), (b"<svg", False),
])
def test_svg_safety(body, valid):
    value = _pane(); value["assets"] = [_asset("icon.svg", "image/svg+xml", body)]; errors, _ = panes.validate_pane(value); assert (not errors) is valid


def test_pane_document_escapes_script_context_and_replaces_prefix_assets():
    pane = _pane()
    pane.update({"pane_html": "asset:ab asset:a", "pane_css": "asset:a asset:ab",
                 "pane_js": "window.assets='asset:ab asset:a'", "assets": [
                     {"name": "a", "media_type": "image/gif", "data_base64": "QQ=="},
                     {"name": "ab", "media_type": "image/gif", "data_base64": "Qg=="},
                 ]})
    payload = "</script><script>window.contextInjection='ran'</script><b>&\u2028\u2029"
    document = glass_routes._pane_document({"pane": pane}, {"instance_id": "one", "data": {"message": payload}}, "2099-01-01", "2099-01-01T08:00:00", None)
    assert "asset:a" not in document and "asset:ab" not in document
    assert document.count("data:image/gif;base64,QQ==") == 3
    assert document.count("data:image/gif;base64,Qg==") == 3
    assert "</script><script>window.contextInjection" not in document
    assert "\\u003c/script\\u003e" in document and "\\u0026" in document


def test_no_schedule_rejects_block_layout_but_allows_default_scene(tmp_path, monkeypatch):
    monkeypatch.setattr("api.schedule.loader.discover_bell_schedule", lambda *_args: (None, []))
    approved = _approved_pane(tmp_path)
    default = _scene(approved["pane_revision"])
    default["blocks"] = {}
    assert panes._block_ids() == set()
    assert panes.save_scene_draft(default, root=str(tmp_path))["ok"]
    blocked = _scene(approved["pane_revision"])
    assert panes.save_scene_draft(blocked, root=str(tmp_path))["ok"] is False


def test_corrupt_drafts_are_ignored_by_listing_and_lookup(tmp_path):
    valid = panes.save_pane_draft(_pane(), root=str(tmp_path))
    review = tmp_path / "To Review" / "Glass"
    unsafe_scene = {"format": panes.SCENE_FORMAT, "date": "2099-01-03", "title": "Unsafe", "default": ["not an instance"], "blocks": {}}
    malformed = [
        ("panes/missing.json", {"kind": "pane", "draft_id": "a" * 32, "pane": _pane()}),
        ("panes/wrong-subject.json", {"kind": "pane", "draft_id": "b" * 32, "digest": valid["digest"], "pane": _pane()}),
        ("scenes/2099-01-01.json", {"kind": "scene", "draft_id": "c" * 32, "digest": "0" * 64, "scene": {"date": "2099-01-02"}}),
        ("scenes/2099-01-03.json", {"kind": "scene", "draft_id": "d" * 32, "digest": panes._scene_digest(unsafe_scene), "scene": unsafe_scene}),
    ]
    for relative, record in malformed:
        path = review / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record), encoding="utf-8")
    assert panes.list_drafts(str(tmp_path)) == [{"draft_id": valid["draft_id"], "kind": "pane",
                                                  "subject": "instruction-pane", "digest": valid["digest"]}]
    for draft_id in ("a" * 32, "b" * 32, "c" * 32, "d" * 32):
        assert panes.draft(draft_id, str(tmp_path)) is None
        assert panes.discard(draft_id, str(tmp_path)) is False


def test_glass_sources_are_public_local_and_current():
    """The Glass-facing source set stays free of private and retired contracts."""
    root = Path(__file__).resolve().parents[3]
    sources = [
        root / "api" / "glass" / "panes.py",
        root / "api" / "webui" / "routes" / "glass.py",
        root / "docs" / "reference" / "glass-module-map.md",
        root / "api" / "default_docs" / "Glass" / "README (Glass contracts).txt",
        root / "api" / "default_docs" / "Glass" / "Glass Pane contract.txt",
        root / "api" / "default_docs" / "Glass" / "Glass Scene contract.txt",
        root / "api" / "mcp_server" / "tool_schema_v11.json",
        root / "api" / "mcp_server" / "server.py",
    ]
    sources.extend((root / "api" / "default_docs" / "Glass").glob("*.json"))
    text = "\n".join(path.read_text(encoding="utf-8") for path in sources)
    assert not re.search(r"https?://", text)
    assert not re.search(r"(?:[A-Za-z]:\\Users\\|/Users/|/home/)", text)
    for retired in ("canvasexpert.day_plan/1", "fixed-board", "widget", "timer", "geometry"):
        assert retired not in text.lower()
    assert "cpu-exhaustion" in text.lower()
    assert "Mockingbird Junior High" in (root / "api" / "default_docs" / "Glass" / "Mockingbird-Junior-High-Sample.json").read_text(encoding="utf-8")
    blocked_host = "invalid" + ".test"
    assert blocked_host not in text
    invalid_test_files = [path.name for path in (root / "api" / "tests" / "glass").glob("*.py")
                          if blocked_host in path.read_text(encoding="utf-8")]
    assert invalid_test_files == ["test_glass_browser.py"]
    from api.mcp_server import contract
    assert not {tool["name"] for tool in contract.load_contract(11)["tools"]
                if "approve" in tool["name"] or "publish" in tool["name"]}


def test_glass_authoring_contracts_are_actionable_without_staging_appendix():
    root = Path(__file__).resolve().parents[3] / "api" / "default_docs" / "Glass"
    pane = (root / "Glass Pane contract.txt").read_text(encoding="utf-8")
    scene = (root / "Glass Scene contract.txt").read_text(encoding="utf-8")
    for term in ("save_glass_pane_draft", "manifest", "pane_html", "pane_css", "pane_js", "data_base64", "data_schema", "example_data", "20", "5 MiB", "20 MiB", "asset:name", "glass:context/2", "sandbox", "network", "storage", "navigation", "student", "immutable", "digest"):
        assert term in pane
    for term in ("save_glass_scene_draft", "default", "blocks", "instance_id", "pane_id", "pane_revision", "column", "row", "width", "height", "JSON", "12x8", "overlap", "atomic", "Teacher approval"):
        assert term in scene
    assert "Staging this for the teacher" not in pane + scene


def test_asset_count_collision_and_digest_stability(monkeypatch):
    value = _pane(); image = _asset("a.png", "image/png", b"\x89PNG\r\n\x1a\n")
    value["assets"] = [dict(image, name=f"{n}.png") for n in range(21)]; errors, _ = panes.validate_pane(value); assert errors
    value["assets"] = [image, dict(image, name="A.PNG")]; errors, _ = panes.validate_pane(value); assert errors
    value["assets"] = [image, _asset("b.gif", "image/gif", b"GIF89a")]; errors, pane = panes.validate_pane(value); assert not errors
    assert panes.pane_digest(pane) == panes.pane_digest({**pane, "assets": list(reversed(pane["assets"]))})
    changed = {**pane, "pane_js": "x"}; assert panes.pane_digest(changed) != panes.pane_digest(pane)


def test_production_asset_limits_and_compact_boundaries(monkeypatch):
    assert (panes._MAX_ASSET, panes._MAX_PACKAGE) == (5 * 1024 * 1024, 20 * 1024 * 1024)
    value = _pane(); image = _asset("a.png", "image/png", b"\x89PNG\r\n\x1a\n")
    value["assets"] = [dict(image, name=f"a{index}.png") for index in range(20)]
    assert not panes.validate_pane(value)[0]
    value["assets"].append(dict(image, name="too-many.png")); assert panes.validate_pane(value)[0]
    monkeypatch.setattr(panes, "_MAX_ASSET", 8); value["assets"] = [image]
    assert not panes.validate_pane(value)[0]
    value["assets"] = [_asset("a.png", "image/png", b"\x89PNG\r\n\x1a\nx")]; assert panes.validate_pane(value)[0]
    monkeypatch.setattr(panes, "_MAX_ASSET", 99)
    base = len(panes._canonical(value["manifest"])) + sum(len(str(value[key]).encode()) for key in ("pane_html", "pane_css", "pane_js"))
    monkeypatch.setattr(panes, "_MAX_PACKAGE", base + 8); value["assets"] = [image]
    assert not panes.validate_pane(value)[0]
    monkeypatch.setattr(panes, "_MAX_PACKAGE", base + 7); assert panes.validate_pane(value)[0]


def test_pane_digest_covers_every_component_and_asset_order():
    pane = _pane(); pane["assets"] = [_asset("a.png", "image/png", b"\x89PNG\r\n\x1a\n"), _asset("b.gif", "image/gif", b"GIF89a")]
    _, pane = panes.validate_pane(pane); digest = panes.pane_digest(pane)
    variants = [
        {**pane, "manifest": {**pane["manifest"], "title": "Changed"}}, {**pane, "pane_html": "<p>Changed</p>"},
        {**pane, "pane_css": ".changed{}"}, {**pane, "pane_js": "var changed=1;"},
        {**pane, "assets": [{**pane["assets"][0], "name": "renamed.png"}, pane["assets"][1]]},
        {**pane, "assets": [{**pane["assets"][0], "media_type": "image/gif"}, pane["assets"][1]]},
        {**pane, "assets": [{**pane["assets"][0], "data_base64": base64.b64encode(b"\x89PNG\r\n\x1a\nx").decode()}, pane["assets"][1]]},
    ]
    assert all(panes.pane_digest(item) != digest for item in variants)
    assert panes.pane_digest({**pane, "assets": list(reversed(pane["assets"]))}) == digest


def test_pending_ids_approval_reuse_and_tamper_refusal(tmp_path):
    value = _pane(); saved = panes.save_pane_draft(value, root=str(tmp_path)); assert saved["ok"]
    assert not panes.save_pane_draft(value, root=str(tmp_path))["ok"]
    assert not panes.approve_pane(saved["draft_id"], "0" * 64, str(tmp_path))["ok"]
    approved = panes.approve_pane(saved["draft_id"], saved["digest"], str(tmp_path)); assert approved["ok"]
    second = panes.save_pane_draft(value, root=str(tmp_path)); reused = panes.approve_pane(second["draft_id"], second["digest"], str(tmp_path)); assert reused["pane_revision"] == approved["pane_revision"]
    folder = tmp_path / "Library" / "Glass" / "panes" / "instruction-pane" / approved["pane_revision"]
    (folder / "pane.html").write_text("tampered", encoding="utf-8")
    assert panes._approved("instruction-pane", approved["pane_revision"], str(tmp_path)) is None
    third = panes.save_pane_draft(value, root=str(tmp_path)); result = panes.approve_pane(third["draft_id"], third["digest"], str(tmp_path)); assert result["ok"] is False and panes.draft(third["draft_id"], str(tmp_path))


def _approved_pane(tmp_path):
    saved = panes.save_pane_draft(_pane(), root=str(tmp_path)); return panes.approve_pane(saved["draft_id"], saved["digest"], str(tmp_path))


def _scene(revision, day="2099-09-14"):
    return {"format": panes.SCENE_FORMAT, "date": day, "title": "Fictional", "default": [{"instance_id":"one","pane_id":"instruction-pane","pane_revision":revision,"data":{"text":"x"},"column":1,"row":1,"width":12,"height":8}], "blocks":{"p2":[]}}


@pytest.mark.parametrize("mutate", [
    lambda s: s.pop("default"), lambda s: s.__setitem__("extra", 1), lambda s: s.__setitem__("date", "bad"), lambda s: s.__setitem__("title", ""), lambda s: s.__setitem__("default", {}), lambda s: s.__setitem__("blocks", []), lambda s: s["blocks"].__setitem__("bad", []), lambda s: s["default"][0].__setitem__("column", True), lambda s: s["default"][0].__setitem__("width", 13),
])
def test_scene_schema_boundaries(tmp_path, mutate):
    approved = _approved_pane(tmp_path); scene = _scene(approved["pane_revision"]); mutate(scene); assert panes.validate_scene(scene, str(tmp_path), {"p2"})


def test_scene_overlap_duplicates_and_storage_integrity(tmp_path):
    approved = _approved_pane(tmp_path); scene = _scene(approved["pane_revision"]); duplicate = dict(scene["default"][0]); scene["default"].append(duplicate); assert panes.validate_scene(scene, str(tmp_path), {"p2"})
    scene = _scene(approved["pane_revision"]); scene["blocks"] = {}; first = panes.save_scene_draft(scene, root=str(tmp_path)); assert first["ok"] and not panes.save_scene_draft(scene, root=str(tmp_path))["ok"]
    assert not panes.approve_scene(first["draft_id"], "0" * 64, str(tmp_path))["ok"]
    published = panes.approve_scene(first["draft_id"], first["digest"], str(tmp_path)); assert published["ok"]
    assert panes.approved_scene(__import__('datetime').date.fromisoformat(scene["date"]), str(tmp_path))
    path = tmp_path / "Library" / "Glass" / "scenes" / f"{scene['date']}.json"; path.write_text("{}", encoding="utf-8")
    assert panes.approved_scene(__import__('datetime').date.fromisoformat(scene["date"]), str(tmp_path)) is None


def test_scene_complete_replacement_and_reference_validation(tmp_path):
    approved = _approved_pane(tmp_path); scene = _scene(approved["pane_revision"]); scene["blocks"] = {"p2": [_scene(approved["pane_revision"])["default"][0]]}
    scene["blocks"]["p2"][0] = {**scene["blocks"]["p2"][0], "instance_id": "replacement", "column": 1, "row": 1}
    assert not panes.validate_scene(scene, str(tmp_path), {"p2"})
    cases = []
    missing = _scene(approved["pane_revision"]); missing["default"][0].pop("width"); cases.append(missing)
    extra = _scene(approved["pane_revision"]); extra["default"][0]["extra"] = 1; cases.append(extra)
    duplicate = _scene(approved["pane_revision"]); duplicate["default"].append(dict(duplicate["default"][0])); cases.append(duplicate)
    boolean = _scene(approved["pane_revision"]); boolean["default"][0]["row"] = True; cases.append(boolean)
    outside = _scene(approved["pane_revision"]); outside["default"][0]["column"] = 13; cases.append(outside)
    overlap = _scene(approved["pane_revision"]); overlap["default"].append({**overlap["default"][0], "instance_id": "two"}); cases.append(overlap)
    revision = _scene("0" * 64); cases.append(revision)
    missing_revision = _scene(approved["pane_revision"]); missing_revision["default"][0].pop("pane_revision"); cases.append(missing_revision)
    data = _scene(approved["pane_revision"]); data["default"][0]["data"] = {"text": 1}; cases.append(data)
    assert all(panes.validate_scene(item, str(tmp_path), {"p2"}) for item in cases)


def test_pending_corrections_are_exact_and_fail_without_writing(tmp_path):
    pane = _pane(); first = panes.save_pane_draft(pane, root=str(tmp_path)); path = tmp_path / "To Review" / "Glass" / "panes" / "instruction-pane.json"
    original = path.read_bytes(); changed = {**pane, "pane_html": "<p>Changed</p>"}
    assert not panes.save_pane_draft(changed, "wrong", str(tmp_path))["ok"] and path.read_bytes() == original
    assert not panes.save_pane_draft(changed, "a" * 32, str(tmp_path))["ok"] and path.read_bytes() == original
    corrected = panes.save_pane_draft(changed, first["draft_id"], str(tmp_path)); assert corrected["ok"] and corrected["digest"] != first["digest"]
    approved = panes.approve_pane(corrected["draft_id"], corrected["digest"], str(tmp_path))
    scene = _scene(approved["pane_revision"]); scene["blocks"] = {}; saved = panes.save_scene_draft(scene, root=str(tmp_path)); scene_path = tmp_path / "To Review" / "Glass" / "scenes" / "2099-09-14.json"; original = scene_path.read_bytes()
    changed_scene = {**scene, "title": "Changed"}
    assert not panes.save_scene_draft(changed_scene, "wrong", str(tmp_path))["ok"] and scene_path.read_bytes() == original
    unknown_scene = {**scene, "date": "2099-09-15"}
    assert not panes.save_scene_draft(unknown_scene, "a" * 32, str(tmp_path))["ok"] and not (tmp_path / "To Review" / "Glass" / "scenes" / "2099-09-15.json").exists()
    assert panes.save_scene_draft(changed_scene, saved["draft_id"], str(tmp_path))["ok"]


def test_scene_replacement_is_scoped_to_its_date_and_atomic_write_cleans_temp(tmp_path, monkeypatch):
    approved = _approved_pane(tmp_path)
    one = _scene(approved["pane_revision"], "2099-09-14"); one["blocks"] = {}; draft = panes.save_scene_draft(one, root=str(tmp_path)); first = panes.approve_scene(draft["draft_id"], draft["digest"], str(tmp_path))
    two = _scene(approved["pane_revision"], "2099-09-15"); two["blocks"] = {}; draft = panes.save_scene_draft(two, root=str(tmp_path)); second = panes.approve_scene(draft["draft_id"], draft["digest"], str(tmp_path))
    replacement = {**one, "title": "Replacement"}; draft = panes.save_scene_draft(replacement, root=str(tmp_path)); replaced = panes.approve_scene(draft["draft_id"], draft["digest"], str(tmp_path))
    assert replaced["digest"] != first["digest"] and panes.approved_scene(__import__('datetime').date(2099, 9, 15), str(tmp_path))["digest"] == second["digest"]
    target = tmp_path / "atomic" / "target.json"; monkeypatch.setattr(panes.os, "replace", lambda *_args: (_ for _ in ()).throw(OSError("fictional")))
    with pytest.raises(OSError): panes._write(target, b"x")
    assert not target.exists() and not list(target.parent.glob(".glass-*"))


def test_display_protocol_source_pins_heartbeat_ready_and_activation_reset():
    source = (Path(__file__).resolve().parents[2] / "webui" / "static" / "glass" / "display.js").read_text(encoding="utf-8")
    assert 'event.data.type === "glass:ready/1" || event.data.type === "glass:heartbeat/1"' in source
    assert "state.ready = false; state.beat = 0; state.started = Date.now()" in source
