"""HTML page routes for Canvas Expert.

One APIRouter; all 9 GET page routes + the /api/open-path utility POST.
Imported by server.py via app.include_router(router).

Routes: GET /, /about, /ai-expert, /assessment, /course, /course-expert,
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
from ..deps import (
    AI_TA_DIR, API_DIR, REPO_ROOT, _CUSTOM_DIR, _key_to_year, templates,
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
    workspace_root = workspace.workspace_root()
    workspace_status = "local folders"
    if workspace_root:
        parts = os.path.normpath(workspace_root).split(os.sep)
        folder = parts[-1] if parts else workspace_root
        workspace_status = f"OneDrive/{folder}" if any("OneDrive" in p for p in parts) else folder
    return templates.TemplateResponse("dashboard.html", {
        "request":        request,
        "nav_section":    "dashboard",
        "token_is_set":   config.token_is_set(),
        "canvas_base":    config.get_canvas_base(),
        "saved_courses":  courses,
        "active_count":   len(courses),
        "workspace_status": workspace_status,
    })


@router.get("/assessment", response_class=HTMLResponse)
def assessment_page(request: Request):
    return RedirectResponse(url="/course-expert", status_code=302)


@router.get("/course-expert", response_class=HTMLResponse)
def course_expert_page(request: Request):
    _skills = list_ai_ta_files()
    def _skill(prefix):
        for f in _skills:
            if f["label"].startswith(prefix):
                return f["label"]
        return ""
    authoring_skills = {
        "quiz":       _skill("Author a Quiz"),
        "assignment": _skill("Author an Assignment"),
        "page":       _skill("Author a Page"),
        "rubric":     _skill("Author a Rubric"),
    }
    return templates.TemplateResponse("course_expert.html", {
        "request":          request,
        "nav_section":      "course",
        "token_is_set":     config.token_is_set(),
        "canvas_base":      config.get_canvas_base(),
        "saved_courses":    config.active_courses(),
        "quiz_files":       list_quiz_files(),
        "assignment_files": list_assignment_files(),
        "page_files":       list_page_files(),
        "authoring_skills": authoring_skills,
    })


@router.get("/ai-expert", response_class=HTMLResponse)
def ai_expert_page(request: Request):
    ai_ta_files = list_ai_ta_files()
    toolkit_dir = os.path.join(AI_TA_DIR, "MagicSchool Toolkit")
    toolkit_files = []
    if os.path.isdir(toolkit_dir):
        toolkit_files = sorted(
            os.path.basename(p)
            for p in glob.glob(os.path.join(toolkit_dir, "*.txt"))
        )
    return templates.TemplateResponse("ai_expert.html", {
        "request":        request,
        "nav_section":    "ai",
        "token_is_set":   config.token_is_set(),
        "ai_ta_files":    ai_ta_files,
        "ai_ta_dir":      AI_TA_DIR,
        "toolkit_files":  toolkit_files,
        "workspace_root": workspace.workspace_root(),
    })


@router.get("/feedback-expert", response_class=HTMLResponse)
def feedback_expert_page(request: Request):
    fb = workspace.feedback_root()
    folders = {}
    if fb:
        folders = {k: workspace.feedback_folder(v) for k, v in {
            "inbox": "1_Inbox", "forllm": "2_ForLLM",
            "fromllm": "3_FromLLM", "toenter": "4_ToEnter",
            "safe": "SAFE", "private": "PRIVATE", "system": "_system"}.items()}
    return templates.TemplateResponse("feedback_expert.html", {
        "request":       request,
        "nav_section":   "feedback",
        "persona":       config.get_ai_ta_persona(),
        "feedback_root": fb,
        "folders":       folders,
        "saved_courses": config.active_courses(),
    })


@router.get("/name-manager", response_class=HTMLResponse)
def name_manager_page(request: Request):
    fb = workspace.feedback_root()
    return templates.TemplateResponse("name_manager.html", {
        "request":       request,
        "nav_section":   "feedback",
        "feedback_root": fb,
        "saved_courses": config.active_courses(),
    })


@router.get("/about", response_class=HTMLResponse)
def about(request: Request):
    return templates.TemplateResponse("about.html", {"request": request, "nav_section": "about"})


@router.get("/course", response_class=HTMLResponse)
def course_page(request: Request, course_id: str = ""):
    """Detailed Course Info page — roster, groups, modules, assignments."""
    return templates.TemplateResponse("course.html", {
        "request":        request,
        "nav_section":    "course",
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
    return templates.TemplateResponse("gradebook.html", {
        "request":              request,
        "nav_section":          "gradebook",
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
    return templates.TemplateResponse("routines.html", {
        "request":          request,
        "nav_section":      "gradebook",
        "token_is_set":     config.token_is_set(),
        **_routines_template_context(),
    })


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    root = workspace.workspace_root()
    return templates.TemplateResponse("settings.html", {
        "request":       request,
        "nav_section":   "",
        "canvas_base":   config.get_canvas_base(),
        "token_is_set":  config.token_is_set(),
        "saved_courses": config.saved_courses(),
        "base_default":  config.CANVAS_BASE_DEFAULT,
        "download_root": config.get_download_root(),
        "ai_ta_dir":     AI_TA_DIR,
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
