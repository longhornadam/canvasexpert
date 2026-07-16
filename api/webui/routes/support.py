"""Server-owned privacy-minimized support bundle download."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from api import diagnostics, runtime_paths


router = APIRouter(tags=["support"])


def _cleanup(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


@router.post("/api/support-bundle")
def support_bundle():
    directory = Path(runtime_paths.temp_dir())
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"CanvasExpert-support-{uuid4().hex}.zip"
    diagnostics.build_support_bundle(destination)
    return FileResponse(
        destination,
        media_type="application/zip",
        filename="CanvasExpert-support-bundle.zip",
        background=BackgroundTask(_cleanup, destination),
    )
