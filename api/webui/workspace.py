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
WORKSPACE_SUBFOLDERS = [
    "AI-TA", "Rubrics", "Quizzes", "Assignments", "Pages", "Exports",
    "Calendars", "Source Materials",
]

# FeedbackExpert zone folders (nested under the workspace).
FEEDBACK_NAME = "FeedbackExpert"
FEEDBACK_SUBFOLDERS = ["SAFE", "PRIVATE", "_system"]


def _ensure_system_subfolders(fb_root):
    """Create _system sub-directories: vault, archive, audit."""
    sys_root = os.path.join(fb_root, "_system")
    for sub in ("vault", "archive", "audit"):
        os.makedirs(os.path.join(sys_root, sub), exist_ok=True)


def _migrate_old_layout(fb_root):
    """One-time migration: move old _vault, _archive, _audit into _system/."""
    sys_root = os.path.join(fb_root, "_system")
    old_new = [
        ("_vault", "vault"),
        ("_archive", "archive"),
        ("_audit", "audit"),
    ]
    for old_name, new_name in old_new:
        old_dir = os.path.join(fb_root, old_name)
        new_dir = os.path.join(sys_root, new_name)
        if os.path.isdir(old_dir) and not os.path.isdir(new_dir):
            shutil.move(old_dir, new_dir)


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

    # FeedbackExpert zone folders.
    fb_root = os.path.join(root, FEEDBACK_NAME)
    for sub in FEEDBACK_SUBFOLDERS:
        os.makedirs(os.path.join(fb_root, sub), exist_ok=True)
    _ensure_system_subfolders(fb_root)
    _migrate_old_layout(fb_root)

    # Seed a READ-ME file at the FeedbackExpert root.
    readme_path = os.path.join(fb_root, "READ-ME (what's safe to share).txt")
    if not os.path.exists(readme_path):
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(
                "Canvas Expert — FeedbackExpert Folder Zones\n"
                "=============================================\n\n"
                "SAFE/       = pseudonymized (fake-name) copies of student work.\n"
                "              Safe to paste into ChatGPT, Claude, MagicSchool, etc.\n\n"
                "PRIVATE/    = real-name originals, who-is-who decoders, raw\n"
                "              downloads. NEVER leaves this PC.\n\n"
                "_system/    = vault database, archives, logs. Don't touch.\n"
            )
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
    """Resolve a FeedbackExpert sub-folder path. Translates legacy names to new zones.
    Legacy: 1_Inbox, 2_ForLLM, 3_FromLLM, 4_ToEnter, _vault, _archive, _audit.
    New:    SAFE, PRIVATE, _system/vault, _system/archive, _system/audit.
    """
    translation = {
        "1_Inbox": "PRIVATE",
        "2_ForLLM": "SAFE",
        "3_FromLLM": "SAFE",
        "4_ToEnter": "PRIVATE",
        "_vault": os.path.join("_system", "vault"),
        "_archive": os.path.join("_system", "archive"),
        "_audit": os.path.join("_system", "audit"),
    }
    resolved = translation.get(sub, sub)
    fb = feedback_root()
    if not fb:
        return None
    return os.path.join(fb, resolved)
