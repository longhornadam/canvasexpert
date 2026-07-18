"""Gradebook school-day sweep routes.

Preview only. Applying a sweep goes through the operation-ledger flow
(``POST /api/operations/gradebook.sweep/prepare`` →
``POST /api/operation-batches/review`` →
``POST /api/operation-batches/{batch_id}/apply`` in
``routes/operations.py``), where ``SweepAdapter`` recomputes the write set
from authoritative Canvas state. Do not reintroduce a direct-PUT apply route
that trusts browser-submitted entries.
"""
import json

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from .. import config
from ..gradebook_service import _sweep_compute

router = APIRouter(tags=["gradebook"])


@router.post("/api/sweep/preview")
def sweep_preview(course_id: str = Form(...), settings: str = Form(...)):
    """Dry run - compute every late deduction + the comment text, change nothing."""
    try:
        s = json.loads(settings)
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": f"bad request: {e}"})
    config.set_sweep_settings(s)
    entries, skipped, err = _sweep_compute(course_id, s)
    if err:
        return JSONResponse({"ok": False, "error": err})
    return JSONResponse({"ok": True, "entries": entries, "skipped": skipped})
