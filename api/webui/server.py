"""Local web UI for Canvas Expert (the live/token half of the platform).

QuizForge is one tool that plugs into this platform; UnitForge and future
forge tools will plug in alongside it.

One Canvas token (stored in the OS keychain, set once on the Settings page)
covers all of the teacher's courses. The teacher picks which course to target
from a live dropdown (or from their saved bookmarks) on the dashboard — no
more separate "profiles" for each class.

Push/dry-run/differentiation still delegate to the existing CLI scripts as
subprocesses (api/qf_pusher.py, push_tiers.py) with credentials injected via
environment variables. See runner.py. Push logic is never touched by this UI.
"""
import os
import sys
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import downloader    # noqa: E402
import student_packet  # noqa: E402

from . import af, ai_ta, activity, config, pf, rf, runner
from . import workspace
from .canvas_client import _canvas_headers, _canvas_get, _canvas_get_all, _canvas_send
from .schooldays import (
    _parse_iso_local, _is_school_day, _school_days_late,
    _school_days_late_detail, _add_school_days,
)

from .deps import (
    WEBUI_DIR, API_DIR, REPO_ROOT,
    _key_to_year, QUIZ_FOLDERS, WORKSPACE_ROOT, _workspace_folder, _exports_dir,
    RUBRIC_FOLDERS, ASSIGNMENT_FOLDERS, PAGE_FOLDERS, AI_TA_DIR, TEMP_DIR, templates,
    _CUSTOM_DIR, list_quiz_files, list_assignment_files, list_page_files,
    list_rubric_files, list_ai_ta_files,
)

from .routes.calendar import router as _calendar_router
from .routes.courses import router as _courses_router
from .routes.feedback import router as _feedback_router
from .routes.names import names_router as _names_router
from .routes.gradebook import router as _gradebook_router
from .routes.library import router as _library_router
from .routes.onboarding import router as _onboarding_router
from .routes.pages import router as _pages_router
from .routes.push import router as _push_router
from .routes.reports import router as _reports_router
from .routes.routines import router as _routines_router, _load_custom_routines, _routines_heartbeat
from .routes.roster import router as _roster_router
from .routes.settings import router as _settings_router
from .routes.powergrader import router as _powergrader_router
from .routes.readiness import router as _readiness_router
from .routes.receipts import router as _receipts_router
from .routes.work import router as _work_router


@asynccontextmanager
async def _lifespan(app):
    """Startup work — kept out of module import so the app is cheap to import
    (route-contract test, tooling). uvicorn fires this when actually serving."""
    try:
        workspace.ensure_workspace()
    except Exception as e:
        print(f"Workspace setup note: {e}")
    try:
        ai_ta.build_library(AI_TA_DIR, rubric_folders=RUBRIC_FOLDERS)
    except Exception as e:
        print(f"AI-TA library build failed: {e}")
    _load_custom_routines()
    threading.Thread(target=_routines_heartbeat, daemon=True).start()
    yield


app = FastAPI(title="Canvas Expert", lifespan=_lifespan)
app.mount("/static", StaticFiles(directory=os.path.join(WEBUI_DIR, "static")), name="static")

# ── Onboarding gate ──────────────────────────────────────────────────────
# If Canvas URL or token is not yet configured, redirect HTML page requests
# to the /welcome wizard. Never gate API/static endpoints or the wizard itself.

_ALLOWLIST_PREFIXES = ("/welcome", "/settings", "/static", "/api", "/openapi.json", "/docs", "/redoc")


@app.middleware("http")
async def _onboarding_gate(request: Request, call_next):
    if not config.token_is_set() or not config.get_canvas_base():
        path = request.url.path
        wants_html = "text/html" in request.headers.get("accept", "")
        allowlisted = any(path.startswith(p) for p in _ALLOWLIST_PREFIXES)
        if wants_html and not allowlisted:
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url="/welcome", status_code=303)
    return await call_next(request)


app.include_router(_onboarding_router)
app.include_router(_calendar_router)
app.include_router(_courses_router)
app.include_router(_feedback_router)
app.include_router(_names_router)
app.include_router(_gradebook_router)
app.include_router(_library_router)
app.include_router(_pages_router)
app.include_router(_push_router)
app.include_router(_reports_router)
app.include_router(_routines_router)
app.include_router(_roster_router)
app.include_router(_settings_router)
app.include_router(_powergrader_router)
app.include_router(_readiness_router)
app.include_router(_receipts_router)
app.include_router(_work_router)
