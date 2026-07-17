"""HTML page routes for Canvas Expert.

One APIRouter; all 9 GET page routes + the /api/open-path utility POST.
Imported by server.py via app.include_router(router).

Routes: GET /, /about, /ai-expert, /course, /course-expert,
        /gradebook, /routines, /settings
        POST /api/open-path
"""
import glob
import json
import os
import subprocess
import sys

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .. import config, workspace
from api import runtime_paths
from ..local_request_guard import csrf_token
from api.operation_ledger import operations as operation_store
from api.operation_ledger import receipts as receipt_store
from . import work as work_routes
from ..deps import (
    API_DIR, REPO_ROOT, _CUSTOM_DIR, _key_to_year, templates,
    list_ai_ta_files, list_assignment_files, list_calendar_files,
    list_page_files, list_quiz_files,
)

router = APIRouter(tags=["pages"])


# --------------------------------------------------------------------------
# Page routes
# --------------------------------------------------------------------------

def _routines_template_context() -> dict:
    """Template values shared by the standalone route and the Gradebook tab."""
    def _entry(name):
        return {"name": name, "path": os.path.normpath(os.path.join(_CUSTOM_DIR, name))}

    custom_active, custom_templates = [], []
    if os.path.isdir(_CUSTOM_DIR):
        for path in sorted(glob.glob(os.path.join(_CUSTOM_DIR, "*.py"))):
            name = os.path.basename(path)
            (custom_templates if name.startswith("_") else custom_active).append(_entry(name))

    return {
        "custom_dir":       os.path.normpath(_CUSTOM_DIR),
        "authoring_path":   os.path.normpath(os.path.join(_CUSTOM_DIR, "AUTHORING.md")),
        "custom_active":    custom_active,
        "custom_templates": custom_templates,
        "active_count":     len(config.active_courses()),
    }


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    courses = config.active_courses()
    initial_jobs, initial_presentations = work_routes.visible_work("all") or ([], {})
    initial_operations = [
        {
            "kind": operation.get("kind"),
            "status": operation.get("status"),
            "target_count": operation.get("target_count"),
        }
        for operation in operation_store.list_operations_pii_minimized()
    ]
    workspace_root = workspace.workspace_root()
    workspace_status = "local folders"
    if workspace_root:
        parts = os.path.normpath(workspace_root).split(os.sep)
        folder = parts[-1] if parts else workspace_root
        workspace_status = f"OneDrive/{folder}" if any("OneDrive" in p for p in parts) else folder
    return templates.TemplateResponse(request, "dashboard.html", {
        "nav_section":    "",
        "token_is_set":   config.token_is_set(),
        "canvas_base":    config.get_canvas_base(),
        "saved_courses":  courses,
        "active_count":   len(courses),
        "workspace_status": workspace_status,
        "csrf_token": csrf_token(),
        "initial_jobs": initial_jobs,
        "initial_presentations": initial_presentations,
        "initial_operations": initial_operations,
        "initial_receipts": receipt_store.list_receipts(),
    })


@router.get("/course-expert", response_class=HTMLResponse)
def course_expert_page(request: Request):
    if request.query_params.get("tab") == "students":
        return RedirectResponse("/students/reports", status_code=307)
    skills = list_ai_ta_files()
    return templates.TemplateResponse(request, "course_expert.html", {
        **_push_base_ctx(request),
        "quiz_files":       list_quiz_files(),
        "assignment_files": list_assignment_files(),
        "page_files":       list_page_files(),
        "authoring_skills": {
            "quiz":       _authoring_skill(skills, "Author a Quiz"),
            "assignment": _authoring_skill(skills, "Author an Assignment"),
            "page":       _authoring_skill(skills, "Author a Page"),
            "rubric":     _authoring_skill(skills, "Author a Rubric"),
        },
    })


@router.get("/students/reports", response_class=HTMLResponse)
def student_reports_page(request: Request):
    """Dedicated Student Reports presentation; report APIs remain in reports.py."""
    return templates.TemplateResponse(request, "student_reports.html", {
        **_push_base_ctx(request),
        "nav_section": "manage",
    })


def _authoring_skill(skills: list, prefix: str) -> str:
    for f in skills:
        if f["label"].startswith(prefix):
            return f["label"]
    return ""


def _push_base_ctx(request: Request) -> dict:
    return {
        "nav_section":   "create",
        "token_is_set":  config.token_is_set(),
        "canvas_base":   config.get_canvas_base(),
        "saved_courses": config.active_courses(),
        "csrf_token":    csrf_token(),
    }


@router.get("/ai-expert", response_class=HTMLResponse)
def ai_expert_page(request: Request):
    ai_ta_files = list_ai_ta_files()
    ai_ta_dir = runtime_paths.ai_ta_dir()
    toolkit_dir = os.path.join(ai_ta_dir, "MagicSchool Toolkit")
    toolkit_files = []
    if os.path.isdir(toolkit_dir):
        toolkit_files = sorted(
            os.path.basename(p)
            for p in glob.glob(os.path.join(toolkit_dir, "*.txt"))
        )
    return templates.TemplateResponse(request, "ai_expert.html", {
        "nav_section":    "help",
        "token_is_set":   config.token_is_set(),
        "ai_ta_files":    ai_ta_files,
        "ai_ta_dir":      str(ai_ta_dir),
        "toolkit_files":  toolkit_files,
        "workspace_root": workspace.workspace_root(),
    })


@router.get("/feedback-expert", response_class=RedirectResponse)
def feedback_expert_page():
    """Keep old bookmarks on the session-bound PowerGrader migration lane."""
    return RedirectResponse("/powergrader?advanced=import", status_code=307)


@router.get("/roster", response_class=HTMLResponse)
def roster_page(request: Request):
    """Roster Console — unified student settings surface."""
    return templates.TemplateResponse(request, "roster.html", {
        "nav_section":   "manage",
        "token_is_set":  config.token_is_set(),
        "canvas_base":   config.get_canvas_base(),
        "saved_courses": config.active_courses(),
    })


@router.get("/name-manager", response_class=HTMLResponse)
def name_manager_page(request: Request):
    """Old Name Manager — redirect to the new Roster Console."""
    return RedirectResponse(url="/roster", status_code=302)


@router.get("/about", response_class=HTMLResponse)
def about(request: Request):
    return templates.TemplateResponse(request, "about.html", {"nav_section": "help"})


@router.get("/course", response_class=HTMLResponse)
def course_page(request: Request, course_id: str = ""):
    """Detailed Course Info page — roster, groups, modules, assignments."""
    return templates.TemplateResponse(request, "course.html", {
        "nav_section":    "manage",
        "token_is_set":   config.token_is_set(),
        "canvas_base":    config.get_canvas_base(),
        "saved_courses":  config.active_courses(),
        "selected_id":    course_id,
        "history":        recent_pushes(),
    })


@router.get("/gradebook", response_class=HTMLResponse)
def gradebook_page(request: Request):
    cals = config.get_calendars()
    all_gp: list = []
    total_days = 0
    for key, cal in cals.items():
        total_days += len(cal.get("no_count_dates", []))
        year = _key_to_year(key)
        for gp in cal.get("grading_periods", []):
            all_gp.append({**gp, "year": year})
    all_gp.sort(key=lambda g: g["start"])
    return templates.TemplateResponse(request, "gradebook.html", {
        "nav_section":          "grade",
        "token_is_set":         config.token_is_set(),
        "canvas_base":          config.get_canvas_base(),
        "saved_courses":        config.active_courses(),
        "calendars":            cals,
        "has_calendars":        bool(cals),
        "all_grading_periods":  all_gp,
        "total_holiday_count":  total_days,
        **_routines_template_context(),
    })


@router.get("/routines", response_class=HTMLResponse)
def routines_page(request: Request):
    """Routines — local automations (built-in + custom) and how to add your own.

    Scans the custom_routines folder so the page can show the real path and the
    files it found (active vs. _-prefixed templates)."""
    return templates.TemplateResponse(request, "routines.html", {
        "nav_section":      "automate",
        "token_is_set":     config.token_is_set(),
        **_routines_template_context(),
    })


def _mirror_relative(age_hours) -> str:
    """Human 'synced N ago' from an age in hours (None → never synced)."""
    if age_hours is None:
        return "not yet"
    minutes = int(age_hours * 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes} min ago"
    hours = int(age_hours)
    if hours < 24:
        return f"{hours} h ago"
    return f"{int(age_hours // 24)} d ago"


def _mirror_settings_context() -> dict:
    """Read-only CanvasMirror freshness for the Settings panel. Never raises."""
    default = {
        "mirror_enabled": False, "mirror_configured": False,
        "mirror_courses": [], "mirror_serve_max_age_hours": 6,
    }
    try:
        from .. import mirror_service
        from api.mirror import store as mirror_store
        status = mirror_service.status()
        now = mirror_store.now_iso()
    except Exception:
        return default
    courses = []
    for course in status.get("courses", []) if isinstance(status, dict) else []:
        passes = course.get("passes", {}) if isinstance(course, dict) else {}
        full = (passes.get("full") or {}).get("last_success_at", "")
        delta = (passes.get("delta") or {}).get("last_success_at", "")
        newest = max(full, delta)  # ISO-Z strings compare lexically
        age = mirror_store.age_hours(newest, now) if newest else None
        courses.append({
            "name": course.get("course_name") or course.get("course_id") or "Course",
            "synced_relative": _mirror_relative(age),
        })
    serve = status.get("serve_max_age_hours", 6)
    if isinstance(serve, float) and serve.is_integer():
        serve = int(serve)
    return {
        "mirror_enabled": bool(status.get("enabled")),
        "mirror_configured": bool(status.get("workspace_configured")),
        "mirror_courses": courses,
        "mirror_serve_max_age_hours": serve,
    }


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    root = workspace.workspace_root()
    saved_courses = config.saved_courses()
    return templates.TemplateResponse(request, "settings.html", {
        **_mirror_settings_context(),
        "nav_section":   "settings",
        "canvas_base":   config.get_canvas_base(),
        "token_is_set":  config.token_is_set(),
        "openrouter_is_set": config.has_openrouter_key(),
        "openrouter_model": config.get_openrouter_model(),
        "default_openrouter_model": config.DEFAULT_OPENROUTER_MODEL,
        "openrouter_model_presets": config.openrouter_model_presets(),
        "saved_courses": saved_courses,
        "current_courses": [course for course in saved_courses if course.get("active", True)],
        "previous_courses": [course for course in saved_courses if not course.get("active", True)],
        "base_default":  config.CANVAS_BASE_DEFAULT,
        "download_root": config.get_download_root(),
        "ai_ta_dir":     str(runtime_paths.ai_ta_dir()),
        "calendars":     config.get_calendars(),
        "calendar_files": list_calendar_files(),
        "workspace_root": root,
        "workspace_files": [
            {"name": "AI-TA", "path": workspace.folder("AI-TA")},
            {"name": "Rubrics", "path": workspace.folder("Rubrics")},
            {"name": "Quizzes", "path": workspace.folder("Quizzes")},
            {"name": "Assignments", "path": workspace.folder("Assignments")},
            {"name": "Pages", "path": workspace.folder("Pages")},
            {"name": "Exports", "path": workspace.folder("Exports")},
            {"name": "Source Materials", "path": workspace.folder("Source Materials")},
            {"name": "Courses (PRIVATE)", "path": workspace.courses_root()},
            {"name": "AI Packets (review before sharing)", "path": workspace.ai_packets_root()},
            {"name": "_System (PRIVATE)", "path": workspace.system_root()},
        ],
        "computer_name": os.environ.get("COMPUTERNAME", "this PC"),
        "tier_tags": config.get_tier_tags(),
        "workspace_status": (root or "no OneDrive found — using local folders"),
        "workspace_is_local": not bool(root),
    })


# --------------------------------------------------------------------------
# OS file-reveal utility (used from multiple page UIs)
# --------------------------------------------------------------------------

def _open_in_os(path):
    """Open a file or folder in the OS file manager. Windows-first."""
    if sys.platform.startswith("win"):
        os.startfile(path)                      # noqa: S606 — local-only desktop app
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def _allowed_open_roots():
    """Real paths the open-path endpoint may reveal — app-known roots only."""
    candidates = [_CUSTOM_DIR, config.get_download_root(),
                  config.get_student_reports_root(), workspace.workspace_root(),
                  os.path.join(REPO_ROOT, "Finished_Exports")]
    roots = []
    for r in candidates:
        if not r:
            continue
        try:
            roots.append(os.path.realpath(r))
        except Exception:
            pass
    return roots


@router.post("/api/open-path")
def api_open_path(path: str = Form(...)):
    """Reveal a file/folder in the OS file manager. Local-only desktop app, but
    restricted to existing paths inside app-known roots so a stray localhost POST
    can't launch an arbitrary executable."""
    rp = os.path.realpath(path)
    if not os.path.exists(rp):
        return JSONResponse({"ok": False, "error": "path not found"})
    inside = False
    for root in _allowed_open_roots():
        try:
            if os.path.commonpath([rp, root]) == root:
                inside = True
                break
        except ValueError:
            continue
    if not inside:
        return JSONResponse({"ok": False, "error": "path not allowed"})
    try:
        _open_in_os(rp)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


# --------------------------------------------------------------------------
# Page-private helpers
# --------------------------------------------------------------------------

def recent_pushes(limit=10):
    p = os.path.join(API_DIR, ".experiment_state.json")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        state = json.load(f)
    return list(reversed(state.get("quizzes", [])))[:limit]
