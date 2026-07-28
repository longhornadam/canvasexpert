"""Web UI trigger for Canvas-sourced writing-record ingest.

One POST endpoint: point it at a course + assignment already visible in the
local Course Catalog and CanvasMirror, and every typed submission on that
assignment enters the writing record, pseudonymously and unscored. Follows
the same shape as `portfolio_merged` (`routes/reports.py:283-341`, backed by
`api/portfolio_service.py`'s `build_merged_portfolios`): the driver is a
generator of progress strings, the route consumes it synchronously into one
JSON response -- no streaming transport of its own, no new persistent state.

Local, disk-read-and-write only. No Canvas call, no Canvas write -- see
`api/dailywriting/canvas_ingest.py` for the read boundary this enforces.
"""
from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from api.dailywriting.canvas_ingest import CanvasIngestError, ingest_canvas_assignment

router = APIRouter(prefix="/api/dailywriting", tags=["dailywriting"])


@router.post("/ingest-canvas")
def ingest_canvas(course_id: str = Form(...), assignment_id: str = Form(...)):
    """Ingest one assignment's typed submissions. Never touches Canvas."""
    log: list[str] = []
    try:
        for line in ingest_canvas_assignment(course_id, assignment_id):
            log.append(line)
    except CanvasIngestError as exc:
        return JSONResponse({"ok": False, "error": str(exc), "log": log})
    return JSONResponse({"ok": True, "log": log})
