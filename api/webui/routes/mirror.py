"""CanvasMirror routes — status and manual sync.

Thin router over ``api/webui/mirror_service.py`` (house pattern: logic in the
service module, routes stay declarative). ``sync-now`` runs synchronously —
a first backfill of a large course can take a minute; the UI should say so.
"""
from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from .. import mirror_service

router = APIRouter(tags=["mirror"])


@router.get("/api/mirror/status")
def mirror_status():
    return JSONResponse(mirror_service.status())


@router.post("/api/mirror/sync-now")
def mirror_sync_now(course_id: str = Form("")):
    results = mirror_service.sync_now(course_id or None)
    ok = bool(results) and all(r.get("ok") for r in results)
    return JSONResponse({"ok": ok, "results": results})
