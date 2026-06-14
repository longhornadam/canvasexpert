"""Workspace helpers for the synced OneDrive content home.

The workspace holds teacher-authored content and synced settings when OneDrive is
available. App code stays local; this module only resolves and seeds folders.
"""
import glob
import json
import os
import shutil


MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
API_DIR = os.path.dirname(MODULE_DIR)
REPO_ROOT = os.path.dirname(API_DIR)
CONFIG_PATH = os.path.join(MODULE_DIR, "config.json")
DEFAULT_DOCS_DIR = os.path.join(API_DIR, "default_docs")
WORKSPACE_NAME = "CanvasExpert"
WORKSPACE_SUBFOLDERS = ["AI-TA", "Rubrics", "Quizzes", "Assignments", "Pages", "Exports", "Calendars"]

# FeedbackExpert numbered drop-folder workflow (nested under the workspace).
FEEDBACK_NAME = "FeedbackExpert"
FEEDBACK_SUBFOLDERS = ["1_Inbox", "2_ForLLM", "3_FromLLM", "4_ToEnter", "_archive",
                       "_vault", "_audit"]


def _machine_config():
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def onedrive_root():
    for name in ("OneDriveCommercial", "OneDrive"):
        path = os.environ.get(name, "").strip()
        if path:
            return path
    return None


def workspace_root():
    machine = _machine_config()
    override = str(machine.get("workspace_path") or "").strip()
    if override:
        return override
    root = onedrive_root()
    if root:
        return os.path.join(root, WORKSPACE_NAME)
    return None


def _default_rubric_files():
    source_dir = os.path.join(DEFAULT_DOCS_DIR, "Rubrics")
    if os.path.isdir(source_dir):
        return sorted(glob.glob(os.path.join(source_dir, "*.txt")))
    return sorted(glob.glob(os.path.join(API_DIR, "rubrics", "*.txt")))


def _seed_folder_if_missing(source_dir, target_dir):
    if not os.path.isdir(source_dir):
        return
    for root, _, files in os.walk(source_dir):
        rel_dir = os.path.relpath(root, source_dir)
        dest_root = target_dir if rel_dir == "." else os.path.join(target_dir, rel_dir)
        os.makedirs(dest_root, exist_ok=True)
        for name in files:
            source = os.path.join(root, name)
            target = os.path.join(dest_root, name)
            if os.path.exists(target):
                continue
            shutil.copy2(source, target)


def ensure_workspace():
    root = workspace_root()
    if not root:
        return None
    os.makedirs(root, exist_ok=True)
    for subfolder in WORKSPACE_SUBFOLDERS:
        target_dir = os.path.join(root, subfolder)
        os.makedirs(target_dir, exist_ok=True)
        _seed_folder_if_missing(os.path.join(DEFAULT_DOCS_DIR, subfolder), target_dir)

    rubric_dir = os.path.join(root, "Rubrics")
    for source in _default_rubric_files():
        target = os.path.join(rubric_dir, os.path.basename(source))
        if os.path.exists(target):
            continue
        shutil.copy2(source, target)

    # FeedbackExpert nested workflow tree.
    fb_root = os.path.join(root, FEEDBACK_NAME)
    for sub in FEEDBACK_SUBFOLDERS:
        os.makedirs(os.path.join(fb_root, sub), exist_ok=True)
    return root


def folder(name):
    root = workspace_root()
    if not root:
        return None
    return os.path.join(root, name)


def feedback_root():
    root = workspace_root()
    if not root:
        return None
    return os.path.join(root, FEEDBACK_NAME)


def feedback_folder(sub):
    fb = feedback_root()
    if not fb:
        return None
    return os.path.join(fb, sub)