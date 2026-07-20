"""CanvasMirror status and asynchronous, read-only manual sync routes."""
from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import JSONResponse

from .. import mirror_service

router = APIRouter(tags=["mirror"])


@router.get("/api/mirror/status")
def mirror_status(plan_id: str = ""):
    return JSONResponse(mirror_service.status(plan_id or None))


@router.post("/api/mirror/sync-now", status_code=202)
def mirror_sync_now(course_id: str = Form(""), scope: list[str] = Form([])):
    try:
        plan_id = mirror_service.enqueue_sync(course_id or None, scope or None)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return JSONResponse(status_code=202, content={"ok": True, "plan_id": plan_id})
