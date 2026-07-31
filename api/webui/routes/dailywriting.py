"""Web UI trigger for Canvas-sourced writing-record ingest.

One POST endpoint: point it at a course + assignment already visible in the
local Course Catalog and CanvasMirror, and every submission on that assignment
enters the writing record, pseudonymously and unscored -- typed responses from
the local mirror, uploaded Word documents through one focused Canvas fetch
each. Follows the same shape as `portfolio_merged` (`routes/reports.py:283-341`,
backed by `api/portfolio_service.py`'s `build_merged_portfolios`): the driver is
a generator of progress strings, the route consumes it synchronously into one
JSON response -- no streaming transport of its own, no new persistent state.

Reads only. Nothing here writes to Canvas, and this trigger is deliberately a
web route rather than an MCP tool: `api/dailywriting/canvas_attachments.py`
carries the reasoning, and the constraint that it stay that way.

The `log` lines can name a student's uploaded filename, which is why this
response belongs to the teacher's own browser and is not something an
assistant is given a way to call.
"""
from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from api.dailywriting.canvas_ingest import CanvasIngestError, ingest_canvas_assignment

router = APIRouter(prefix="/api/dailywriting", tags=["dailywriting"])


@router.post("/ingest-canvas")
def ingest_canvas(course_id: str = Form(...), assignment_id: str = Form(...)):
    """Ingest one assignment's submissions, typed or uploaded. Never writes."""
    log: list[str] = []
    try:
        for line in ingest_canvas_assignment(course_id, assignment_id):
            log.append(line)
    except CanvasIngestError as exc:
        return JSONResponse({"ok": False, "error": str(exc), "log": log})
    return JSONResponse({"ok": True, "log": log})
