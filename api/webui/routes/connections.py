"""Local copy-only MCP connection guidance routes."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.background import BackgroundTask

from api import __version__, connections, runtime_paths
from ..deps import templates


router = APIRouter(tags=["connections"])


def _cleanup(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _download_path(suffix: str) -> Path:
    directory = Path(runtime_paths.temp_dir())
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"CanvasExpert-{uuid4().hex}{suffix}"


@router.get("/connections", response_class=HTMLResponse)
def connections_page(request: Request):
    return templates.TemplateResponse(request, "connections.html", {
        "nav_section": "connections",
        "connection": connections.connection_context(),
    })


@router.get("/api/connections/health")
def connections_health():
    return JSONResponse(connections.connection_context()["health"])


@router.post("/api/connections/claude-package")
def claude_package():
    destination = _download_path(".mcpb")
    connections.build_claude_mcpb(destination)
    return FileResponse(
        destination,
        media_type="application/zip",
        filename=f"CanvasExpert-{__version__}.mcpb",
        background=BackgroundTask(_cleanup, destination),
    )
