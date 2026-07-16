"""Shared stable paths, call-time workspace facades, and templates.

Sits BELOW the routers in the import graph: server.py and every future
routes/*.py import from here, and this module imports nothing from them. Stable
application paths remain available here; workspace-derived paths are delegated
to ``runtime_paths`` at call time.
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

from api import __version__, runtime_paths
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
    return runtime_paths.workspace_folder(name)


def _exports_dir():
    """Where printable (DOCX) versions land: the synced workspace Exports folder
    when OneDrive is present, else the repo-local Finished_Exports fallback."""
    return runtime_paths.exports_dir()


# Stable compatibility facade; workspace-derived paths remain call-time only.
TEMP_DIR = str(runtime_paths.temp_dir())

templates = Jinja2Templates(directory=os.path.join(WEBUI_DIR, "templates"))
# Cache-bust static assets on every server restart so UI updates land without
# a hard refresh.
templates.env.globals["asset_v"] = str(int(time.time()))
templates.env.globals["app_version"] = __version__


# --------------------------------------------------------------------------
# Path constant — custom routines directory (used by pages and routines API)
# --------------------------------------------------------------------------
_CUSTOM_DIR = os.path.join(WEBUI_DIR, "..", "custom_routines")


# --------------------------------------------------------------------------
# File-listing helpers (pure; resolve workspace folders at call time)
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
            try:
                label = os.path.relpath(path, REPO_ROOT)
            except ValueError:
                label = os.path.basename(path)
            found.append({
                "label": label,
                "path":  abspath,
            })
    return found


def list_quiz_files():
    return _list_txt_files(runtime_paths.content_folders("quiz"))


def list_assignment_files():
    return _list_txt_files(runtime_paths.content_folders("assignment"))


def list_page_files():
    return _list_txt_files(runtime_paths.content_folders("page"))


def list_rubric_files():
    return _list_txt_files(runtime_paths.rubric_folders())


def list_ai_ta_files():
    found = []
    ai_ta_dir = runtime_paths.ai_ta_dir()
    if not os.path.isdir(ai_ta_dir):
        return found
    for path in sorted(_glob.glob(os.path.join(ai_ta_dir, "*.txt"))):
        found.append({
            "label": os.path.basename(path),
            "path": os.path.abspath(path),
        })
    return found
