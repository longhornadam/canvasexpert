"""Full-screen Glass classroom display routes."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from api.webui import deps, glass_board


router = APIRouter()


def _effective_at(value: str):
    return value.strip() or None


@router.get("/glass", response_class=HTMLResponse)
def glass_page(request: Request, at: str = ""):
    payload = glass_board.get_display_context(_effective_at(at))
    return deps.templates.TemplateResponse(request, "glass.html", {
        "payload": payload,
    })


@router.get("/glass/data")
def glass_data(at: str = ""):
    return JSONResponse(glass_board.get_display_context(_effective_at(at)))
