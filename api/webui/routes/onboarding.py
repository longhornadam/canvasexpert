"""Onboarding wizard routes — first-run setup for Canvas Expert.

These routes drive the stepped welcome flow (workspace → Canvas URL → API token
→ optional calendars) for brand-new users. Once configured, the gate in server.py
redirects unconfigured users here.

Routes: GET  /welcome
        POST /welcome/workspace
"""
import os

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse

from .. import config, workspace
from ..deps import templates

router = APIRouter(tags=["onboarding"])


@router.get("/welcome")
def welcome_page(request: Request):
    """Render the stepped onboarding wizard."""
    # Suggest the OneDrive workspace when available, else a home-dir folder —
    # always a complete, sensible path (never a bare "\CanvasExpert").
    existing = config.get_workspace_path()
    base = workspace.onedrive_root() or os.path.expanduser("~")
    suggestion = existing or os.path.join(base, workspace.WORKSPACE_NAME)
    return templates.TemplateResponse(request, "welcome.html", {
        "nav_section":         "",
        "workspace_suggestion": suggestion,
        "canvas_base":         config.get_canvas_base(),
        "token_is_set":        config.token_is_set(),
    })


@router.post("/welcome/workspace")
def set_workspace(path: str = Form(...)):
    """Save the workspace path and seed it with default folders/files."""
    stripped = path.strip()
    if not stripped:
        return JSONResponse({"ok": False, "error": "Path cannot be empty"})
    config.set_workspace_path(stripped)
    root = workspace.ensure_workspace()
    return JSONResponse({
        "ok": True,
        "root": root,
        "subfolders": [
            workspace.LIBRARY_NAME, workspace.TO_REVIEW_NAME,
            workspace.PRINTABLES_NAME, workspace.CANVAS_UPLOADS_NAME,
            workspace.STUDENT_WORK_NAME, workspace.FOR_AI_NAME,
        ],
    })
