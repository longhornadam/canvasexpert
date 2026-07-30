"""Local Glass review, preview, and opaque-origin projector display."""
from __future__ import annotations

import base64
import json
from datetime import datetime

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from api.glass import panes
from api.glass.day_context import day_context
from .. import config
from ..deps import templates
from ..local_request_guard import csrf_token, require_local_mutation

router = APIRouter(tags=["glass"])

# The one-way context a pane receives. Version 2 added `events`; a pane reads
# only the fields the Glass pane contract enumerates.
GLASS_CONTEXT_TYPE = "glass:context/2"


def _instant(raw: str):
    try: return datetime.fromisoformat(raw), True
    except (TypeError, ValueError): return datetime.now(), False


def _script_json(value) -> str:
    """Serialize JSON safely for an inline script without changing its value."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).translate(str.maketrans({
        "<": "\\u003c", ">": "\\u003e", "&": "\\u0026",
        "\u2028": "\\u2028", "\u2029": "\\u2029",
    }))


def _pane_document(package, instance, scene_date, local_time, current_block, events=None):
    pane = package["pane"]
    assets = {item["name"]: f"data:{item['media_type']};base64,{item['data_base64']}" for item in pane["assets"]}
    def inline(value):
        for name, uri in sorted(assets.items(), key=lambda item: len(item[0]), reverse=True):
            value = value.replace(f"asset:{name}", uri)
        return value
    context = {"type": GLASS_CONTEXT_TYPE, "instance_id": instance["instance_id"], "scene_date": scene_date, "data": instance["data"], "local_time": local_time, "current_block": current_block, "events": events or []}
    csp = "default-src 'none'; connect-src 'none'; frame-src 'none'; object-src 'none'; form-action 'none'; base-uri 'none'; img-src data: blob:; media-src data: blob:; font-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'"
    bootstrap = f"window.glassContext={_script_json(context)};window._glassFailed=false;window._glassFail=function(){{if(window._glassFailed)return;window._glassFailed=true;clearInterval(window._glassHeartbeat);parent.postMessage({{type:'glass:error/1',instance_id:window.glassContext.instance_id}},'*')}};window.addEventListener('error',window._glassFail);window.addEventListener('unhandledrejection',window._glassFail);window.addEventListener('message',function(e){{if(e.data&&e.data.type==='{GLASS_CONTEXT_TYPE}')window.glassContext=e.data}});parent.postMessage({{type:'glass:ready/1',instance_id:window.glassContext.instance_id}},'*');window._glassHeartbeat=setInterval(function(){{parent.postMessage({{type:'glass:heartbeat/1',instance_id:window.glassContext.instance_id}},'*')}},1000);"
    return f"<!doctype html><meta http-equiv=\"Content-Security-Policy\" content=\"{csp}\"><style>{inline(pane['pane_css'])}</style>{inline(pane['pane_html'])}<script>{bootstrap}</script><script>{inline(pane['pane_js'])}</script>"


def _scene_view(record, instant):
    # One merged read for schedule and calendar alike. The calendar used to be
    # read only when a bell schedule existed, so a teacher who had loaded a
    # calendar but not yet filled in a schedule saw no events at all.
    context = day_context(instant)
    blocks = context["blocks"]
    current = context["current_block"]["id"] if context["current_block"] else None
    events = context["events"]
    scene = record["scene"] if record else None
    layouts = {} if not scene else {"default": scene["default"], **scene.get("blocks", {})}
    active = current if current in layouts else "default"
    frames = []
    for layout, instances in layouts.items():
        for instance in instances:
            package = panes._approved(instance["pane_id"], instance["pane_revision"])
            if package: frames.append({"layout": layout, "instance": instance, "srcdoc": _pane_document(package, instance, scene["date"], instant.isoformat(), context["current_block"], events)})
            else: frames.append({"layout": layout, "instance": instance, "failed": True})
    status = "No approved scene for today." if not scene else ("Some content is unavailable." if any(frame.get("failed") for frame in frames) else "Ready.")
    return {"scene": scene, "frames": frames, "layouts": list(layouts), "blocks": blocks, "current": current, "active": active, "at": instant.isoformat(), "status": status, "events": events}


def _pane_only_display(package, instant, digest):
    """A single pane filling the grid, shown with its own example data."""
    instance = {"instance_id": "preview", "pane_id": package["pane"]["manifest"]["id"], "pane_revision": digest,
                "data": package["pane"]["manifest"]["example_data"], "column": 1, "row": 1, "width": 12, "height": 8}
    return {"scene": {"date": "preview", "default": [instance]},
            "frames": [{"layout": "default", "instance": instance, "srcdoc": _pane_document(package, instance, "preview", instant.isoformat(), None)}],
            "layouts": ["default"], "blocks": [], "current": None, "active": "default", "at": instant.isoformat(), "status": "Ready."}


def _review_cards():
    cards = []
    for summary in panes.list_drafts():
        record = panes.draft(summary["draft_id"])
        if not record: continue
        if record["kind"] == "pane":
            pane = record["pane"]; errors, _ = panes.validate_pane(pane)
            cards.append({**summary, "title": pane["manifest"].get("title"), "description": pane["manifest"].get("description"), "example": json.dumps(pane["manifest"].get("example_data"), indent=2), "valid": not errors, "errors": errors, "assets": [{"name": item["name"], "media_type": item["media_type"], "bytes": len(base64.b64decode(item["data_base64"]))} for item in pane["assets"]]})
        else:
            scene = record["scene"]; errors = panes.validate_scene(scene, block_ids=panes._block_ids())
            revisions = [f"{item.get('pane_id')}@{item.get('pane_revision')}" for layout in [scene.get("default", [])] + list(scene.get("blocks", {}).values()) for item in layout]
            cards.append({**summary, "title": scene.get("title"), "date": scene.get("date"), "layouts": ["default", *scene.get("blocks", {}).keys()], "revisions": revisions, "valid": not errors, "errors": errors, "fresh": not errors})
    return cards


@router.get("/glass", response_class=HTMLResponse)
def glass_page(request: Request):
    return templates.TemplateResponse(request, "glass.html", {"nav_section": "glass", "token_is_set": config.token_is_set(), "csrf_token": csrf_token(), "drafts": _review_cards(), "library": panes.list_approved()})


@router.get("/glass/display", response_class=HTMLResponse)
def glass_display(request: Request, at: str = Query("")):
    instant, frozen = _instant(at); return templates.TemplateResponse(request, "glass_display.html", {"display": _scene_view(panes.approved_scene(instant.date()), instant), "frozen": frozen})


@router.get("/glass/preview/{draft_id}", response_class=HTMLResponse)
def glass_preview(request: Request, draft_id: str, layout: str = Query("")):
    record = panes.draft(draft_id)
    if not record: return HTMLResponse("Draft not found", status_code=404)
    instant = datetime.now()
    if record["kind"] == "pane":
        display = _pane_only_display({"pane": record["pane"]}, instant, record["digest"])
    else:
        display = _scene_view(record, instant)
        if layout in display["layouts"]:
            display["active"] = layout
            display["forced_layout"] = layout
    return templates.TemplateResponse(request, "glass_display.html", {"display": display, "frozen": True, "preview_digest": record["digest"]})


@router.get("/glass/library/panes/{pane_id}/{revision}", response_class=HTMLResponse)
def glass_library_pane(request: Request, pane_id: str, revision: str):
    package = panes._approved(pane_id, revision)
    if not package: return HTMLResponse("Approved pane not found", status_code=404)
    return templates.TemplateResponse(request, "glass_display.html", {"display": _pane_only_display(package, datetime.now(), revision), "frozen": True, "preview_digest": revision})


@router.get("/api/glass/drafts")
def glass_drafts(): return JSONResponse({"ok": True, "drafts": panes.list_drafts()})


@router.post("/api/glass/drafts/{draft_id}/approve")
async def glass_approve(request: Request, draft_id: str):
    require_local_mutation(request); payload = await request.json(); record = panes.draft(draft_id)
    result = panes.approve_pane(draft_id, payload.get("digest", "")) if record and record.get("kind") == "pane" else panes.approve_scene(draft_id, payload.get("digest", ""))
    return JSONResponse(result, status_code=200 if result.get("ok") else 400)


@router.post("/api/glass/drafts/{draft_id}/discard")
def glass_discard(request: Request, draft_id: str):
    require_local_mutation(request); return JSONResponse({"ok": panes.discard(draft_id)})
