"""Fictional review-route contract checks for Glass drafts."""
from datetime import datetime

from fastapi.testclient import TestClient
from api.glass import panes
from api.schedule import loader
from api.webui.server import app
from api.webui import workspace
from api.webui.routes import glass as glass_routes
from api.webui.local_request_guard import csrf_token


def _pane():
    return {"manifest":{"format":panes.PANE_FORMAT,"id":"review-pane","title":"Review pane","description":"Fictional description","data_schema":{"type":"object"},"example_data":{"message":"hello"}},"pane_html":"<p>Preview</p>","pane_css":"","pane_js":"","assets":[]}


def test_review_cards_preview_and_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    saved=panes.save_pane_draft(_pane(),root=str(tmp_path)); client=TestClient(app,base_url="http://127.0.0.1:8765")
    page=client.get("/glass"); assert page.status_code==200
    for text in ("Pending panes","Pending scenes","Review pane","Fictional description",saved["digest"],"message","16:9","16:10","aria-pressed","Pane preview"): assert text in page.text
    preview=client.get(f"/glass/preview/{saved['draft_id']}"); assert preview.status_code==200 and saved["digest"] in preview.text and 'sandbox="allow-scripts"' in preview.text
    assert client.get("/glass/preview/unknown").status_code==404
    empty=client.get("/glass/display?at=2099-01-01T08:00:00"); assert "No approved scene for today." in empty.text and 'id="glass-status">No approved scene for today.' in empty.text


def test_review_mutations_require_guard_and_digest(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path)); saved=panes.save_pane_draft(_pane(),root=str(tmp_path)); client=TestClient(app,base_url="http://127.0.0.1:8765")
    assert client.post(f"/api/glass/drafts/{saved['draft_id']}/approve",json={"digest":saved["digest"]}).status_code==403
    assert client.post(f"/api/glass/drafts/{saved['draft_id']}/discard").status_code==403


def test_review_mutations_with_csrf_keep_exact_drafts(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    first = panes.save_pane_draft(_pane(), root=str(tmp_path))
    other = _pane(); other["manifest"] = {**other["manifest"], "id": "other-pane", "title": "Other pane"}
    second = panes.save_pane_draft(other, root=str(tmp_path))
    client = TestClient(app, base_url="http://127.0.0.1:8765"); headers = {"X-CanvasExpert-CSRF": csrf_token()}
    wrong = client.post(f"/api/glass/drafts/{first['draft_id']}/approve", json={"digest": "0" * 64}, headers=headers)
    assert wrong.status_code == 400 and panes.draft(first["draft_id"], str(tmp_path)) is not None
    approved = client.post(f"/api/glass/drafts/{first['draft_id']}/approve", json={"digest": first["digest"]}, headers=headers)
    assert approved.status_code == 200 and approved.json()["pane_revision"] == first["digest"] and panes.draft(first["draft_id"], str(tmp_path)) is None
    discarded = client.post(f"/api/glass/drafts/{second['draft_id']}/discard", headers=headers)
    assert discarded.json() == {"ok": True} and panes.draft(second["draft_id"], str(tmp_path)) is None


def test_only_bundled_fonts_allow_opaque_frame_cors():
    client = TestClient(app, base_url="http://127.0.0.1:8765")
    font = client.get("/static/fonts/public-sans-400.woff2")
    script = client.get("/static/glass/display.js")
    assert font.status_code == 200 and font.headers.get("access-control-allow-origin") == "*"
    assert script.status_code == 200 and "access-control-allow-origin" not in script.headers


def test_review_ignores_corrupt_draft_records(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    path = tmp_path / "To Review" / "Glass" / "panes" / "broken.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"kind":"pane","draft_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}', encoding="utf-8")
    client = TestClient(app, base_url="http://127.0.0.1:8765")
    response = client.get("/glass")
    assert response.status_code == 200 and "No pending pane drafts." in response.text


def test_instant_degrades_when_called_with_none():
    _instant, frozen = glass_routes._instant(None)
    assert frozen is False and _instant.tzinfo is None


def test_stale_scene_draft_stays_reviewable_but_cannot_approve(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    pane = panes.save_pane_draft(_pane(), root=str(tmp_path))
    approved = panes.approve_pane(pane["draft_id"], pane["digest"], str(tmp_path))
    scene = {"format": panes.SCENE_FORMAT, "date": "2099-09-14", "title": "Stale fictional scene",
             "default": [{"instance_id": "one", "pane_id": approved["pane_id"], "pane_revision": approved["pane_revision"],
                          "data": {"message": "hello"}, "column": 1, "row": 1, "width": 12, "height": 8}], "blocks": {}}
    saved = panes.save_scene_draft(scene, root=str(tmp_path))
    revision = tmp_path / "Library" / "Glass" / "panes" / approved["pane_id"] / approved["pane_revision"]
    for child in revision.rglob("*"):
        if child.is_file(): child.unlink()
    for child in sorted(revision.rglob("*"), reverse=True):
        if child.is_dir(): child.rmdir()
    revision.rmdir()

    assert panes.draft(saved["draft_id"], str(tmp_path)) is not None
    assert panes.list_drafts(str(tmp_path)) == [{"draft_id": saved["draft_id"], "kind": "scene", "subject": "2099-09-14", "digest": saved["digest"]}]
    page = TestClient(app, base_url="http://127.0.0.1:8765").get("/glass")
    assert "stale or invalid" in page.text and "must name an approved pane revision" in page.text
    assert f'data-glass-approve="{saved["draft_id"]}" data-glass-digest="{saved["digest"]}" disabled' in page.text
    assert panes.approve_scene(saved["draft_id"], saved["digest"], str(tmp_path))["ok"] is False
    assert panes.discard(saved["draft_id"], str(tmp_path)) is True


def test_scene_view_respects_selected_calendar_no_school_date(monkeypatch):
    schedule = loader.parse_bell_schedule({"format": "canvasexpert.bell_schedule/1", "day_types": {"d": {"blocks": [
        {"id": "p1", "start": "08:30", "end": "09:30"}
    ]}}, "weekday_default": {"0": "d"}})
    monkeypatch.setattr(loader, "discover_bell_schedule", lambda *_args: (schedule, []))
    monkeypatch.setattr(glass_routes.config, "get_combined_calendar_for_range", lambda *_args: {
        "no_count_dates": ["2099-09-14", "not-a-date", None]})
    record = {"scene": {"date": "2099-09-14", "default": [], "blocks": {"p1": []}}}

    display = glass_routes._scene_view(record, datetime(2099, 9, 14, 8, 45))

    assert display["blocks"] == [] and display["current"] is None and display["active"] == "default"


def test_display_keeps_approved_scene_when_one_pane_revision_is_corrupt(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    first = panes.save_pane_draft(_pane(), root=str(tmp_path))
    approved_first = panes.approve_pane(first["draft_id"], first["digest"], str(tmp_path))
    other_pane = _pane(); other_pane["manifest"] = {**other_pane["manifest"], "id": "peer-pane", "title": "Peer pane"}
    second = panes.save_pane_draft(other_pane, root=str(tmp_path))
    approved_second = panes.approve_pane(second["draft_id"], second["digest"], str(tmp_path))
    scene = {"format": panes.SCENE_FORMAT, "date": "2099-09-17", "title": "Two fictional panes", "blocks": {}, "default": [
        {"instance_id": "healthy", "pane_id": approved_first["pane_id"], "pane_revision": approved_first["pane_revision"], "data": {"message": "hello"}, "column": 1, "row": 1, "width": 6, "height": 8},
        {"instance_id": "corrupt", "pane_id": approved_second["pane_id"], "pane_revision": approved_second["pane_revision"], "data": {"message": "hello"}, "column": 7, "row": 1, "width": 6, "height": 8},
    ]}
    draft = panes.save_scene_draft(scene, root=str(tmp_path))
    assert panes.approve_scene(draft["draft_id"], draft["digest"], str(tmp_path))["ok"]
    (tmp_path / "Library" / "Glass" / "panes" / approved_second["pane_id"] / approved_second["pane_revision"] / "package.json").unlink()

    assert panes.approved_scene(__import__("datetime").date(2099, 9, 17), str(tmp_path)) is not None
    page = TestClient(app, base_url="http://127.0.0.1:8765").get("/glass/display?at=2099-09-17T08:45:00")
    assert page.status_code == 200 and "No approved scene for today." not in page.text
    assert page.text.count("Pane unavailable.") == 1 and 'data-instance="healthy"' in page.text and 'data-instance="corrupt"' in page.text
    assert 'data-glass-column="7" data-glass-row="1" data-glass-width="6" data-glass-height="8"' in page.text
    assert 'id="glass-status">Some content is unavailable.' in page.text
