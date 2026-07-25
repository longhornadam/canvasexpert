"""Self-update routes: teacher-initiated only, never polled or automatic.

One APIRouter; all 4 update routes. Thin pass-throughs to self_update.py,
which owns every download/verify/stage rule.

Routes: GET  /api/update/status
        POST /api/update/download
        POST /api/update/apply
        POST /api/update/cancel
"""
from __future__ import annotations

import threading

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import self_update

router = APIRouter(tags=["updates"])


@router.get("/api/update/status")
def update_status():
    return JSONResponse(self_update.status())


@router.post("/api/update/download")
def update_download():
    return JSONResponse(self_update.download_update())


@router.post("/api/update/apply")
def update_apply(request: Request):
    if not self_update.is_staged():
        return JSONResponse(
            {"ok": False, "error": "No update is ready to install. Download one first."},
            status_code=409,
        )
    restart = getattr(request.app.state, "request_restart", None)
    if restart is None:
        return JSONResponse(
            {
                "ok": False,
                "error": (
                    "This app wasn't started from \"Open Canvas Expert.bat\", so it can't "
                    "restart itself. Close it and reopen it from that file."
                ),
            },
            status_code=409,
        )
    # Respond first, then shut down -- the teacher's browser needs to see
    # {"ok": true} before the server actually stops.
    threading.Timer(0.5, restart, args=(7,)).start()
    return JSONResponse({"ok": True, "restarting": True})


@router.post("/api/update/cancel")
def update_cancel():
    return JSONResponse(self_update.cancel_staged())
