"""Shared singletons & path constants for the Canvas Expert web app.

Sits BELOW the routers in the import graph: server.py and every future
routes/*.py import from here, and this module imports nothing from them. Holds
the repo/workspace paths, the per-Forge content-folder lists, small path
helpers, and the Jinja2 templates instance — so splitting routers out of
server.py never creates an import cycle.

Import is cheap/side-effect-free except one trivial mkdir (TEMP_DIR); the heavy
startup work lives in server.init_app.
"""
import glob as _glob
import json as _json
import os
import time


def _sse(lines):
    """Encode an iterable of strings as Server-Sent Events."""
    for line in lines:
        yield f"data: {_json.dumps(line)}\n\n"

from fastapi.templating import Jinja2Templates

from . import workspace

WEBUI_DIR = os.path.dirname(os.path.abspath(__file__))
API_DIR   = os.path.dirname(WEBUI_DIR)
REPO_ROOT = os.path.dirname(API_DIR)

# Calendar CSVs live in the OneDrive workspace (seeded from api/default_docs/Calendars/
# on first run via workspace.ensure_workspace). Resolved lazily so this module stays
# importable even before the workspace is set up.
def _calendars_dir():
    from . import workspace as _ws
    return _ws.folder("Calendars")


def _calendar_label(filename: str) -> str:
    """'Summer_Session_Sample.csv' → 'Summer Session Sample' (district-agnostic)."""
    stem = os.path.splitext(filename)[0]
    return stem.replace("_", " ").replace("-", " ").strip()


def list_calendar_files():
    """CSV calendars available in the user's workspace Calendars folder.

    Data-driven: whatever the teacher (or the first-run seed) placed in the
    Calendars folder shows up here. No district names are baked into source.
    Returns [{name, label, path}] sorted by name.
    """
    cal_dir = _calendars_dir()
    if not cal_dir or not os.path.isdir(cal_dir):
        return []
    found = []
    for path in sorted(_glob.glob(os.path.join(cal_dir, "*.csv"))):
        name = os.path.basename(path)
        found.append({
            "name":  name,
            "label": _calendar_label(name),
            "path":  os.path.abspath(path),
        })
    return found


def _key_to_year(key: str) -> str:
    """'something_2025_26' → '25-26', 'custom' → ''"""
    import re as _re
    m = _re.search(r'(\d{4})_(\d{2})$', key)
    return f"{m.group(1)[-2:]}-{m.group(2)}" if m else ""


def _workspace_folder(name: str):
    return workspace.folder(name)


def _exports_dir():
    """Where printable (DOCX) versions land: the synced workspace Exports folder
    when OneDrive is present, else the repo-local Finished_Exports fallback."""
    return _workspace_folder("Exports") or os.path.join(REPO_ROOT, "Finished_Exports")


# Workspace path is resolved at import (pure); directory creation + seeding
# happens at server startup (server.init_app), so importing this module stays
# side-effect-free and cheap (tests, tooling).
WORKSPACE_ROOT = workspace.workspace_root()

QUIZ_FOLDERS = [
    os.path.join(API_DIR,   "qf_materials", "qf quiz examples"),
    os.path.join(REPO_ROOT, "DropZone"),
    os.path.join(REPO_ROOT, "Finished_Exports"),
]
if _workspace_folder("Quizzes"):
    QUIZ_FOLDERS.append(_workspace_folder("Quizzes"))

RUBRIC_FOLDERS = []
if _workspace_folder("Rubrics"):
    RUBRIC_FOLDERS.append(_workspace_folder("Rubrics"))
RUBRIC_FOLDERS.append(os.path.join(API_DIR, "rubrics"))

ASSIGNMENT_FOLDERS = [os.path.join(API_DIR, "qf_materials", "qf quiz examples")]
if _workspace_folder("Assignments"):
    ASSIGNMENT_FOLDERS.append(_workspace_folder("Assignments"))

PAGE_FOLDERS = [os.path.join(API_DIR, "qf_materials", "qf quiz examples")]
if _workspace_folder("Pages"):
    PAGE_FOLDERS.append(_workspace_folder("Pages"))

AI_TA_DIR = _workspace_folder("AI-TA") or os.path.join(REPO_ROOT, "AI-TA")

TEMP_DIR = os.path.join(API_DIR, "temp")
os.makedirs(TEMP_DIR, exist_ok=True)

templates = Jinja2Templates(directory=os.path.join(WEBUI_DIR, "templates"))
# Cache-bust static assets on every server restart so UI updates land without
# a hard refresh.
templates.env.globals["asset_v"] = str(int(time.time()))


# --------------------------------------------------------------------------
# Path constant — custom routines directory (used by pages and routines API)
# --------------------------------------------------------------------------
_CUSTOM_DIR = os.path.join(WEBUI_DIR, "..", "custom_routines")


# --------------------------------------------------------------------------
# File-listing helpers (pure; depend only on the folder constants above)
# --------------------------------------------------------------------------

def _list_txt_files(folders):
    found = []
    seen = set()
    for folder in folders:
        if not folder or not os.path.isdir(folder):
            continue
        for path in sorted(_glob.glob(os.path.join(folder, "*.txt"))):
            abspath = os.path.abspath(path)
            if abspath in seen:
                continue
            seen.add(abspath)
            found.append({
                "label": os.path.relpath(path, REPO_ROOT),
                "path":  abspath,
            })
    return found


def list_quiz_files():
    return _list_txt_files(QUIZ_FOLDERS)


def list_assignment_files():
    return _list_txt_files(ASSIGNMENT_FOLDERS)


def list_page_files():
    return _list_txt_files(PAGE_FOLDERS)


def list_rubric_files():
    return _list_txt_files(RUBRIC_FOLDERS)


def list_ai_ta_files():
    found = []
    if not os.path.isdir(AI_TA_DIR):
        return found
    for path in sorted(_glob.glob(os.path.join(AI_TA_DIR, "*.txt"))):
        found.append({
            "label": os.path.basename(path),
            "path": os.path.abspath(path),
        })
    return found