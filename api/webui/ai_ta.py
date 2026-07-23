"""AI Authoring library builder: seeds a teacher's workspace with the paste-ready
MagicSchool / Copilot skill files that live at ``api/default_docs/AI Authoring/``.

That folder is the sole repository source for these files -- every "Author a ...",
START HERE, Reference, and MagicSchool Toolkit file there is already the exact
paste-ready text a teacher pastes into an AI assistant. This module never
regenerates that text; it only seeds it into a teacher's workspace (once, never
overwriting an edit) and adds one scoring skill per rubric currently on file,
which cannot be static since it depends on the teacher's own rubric library.

Pure module: builds plain-text output files only. The web UI / server owns the
HTTP routes and startup hook.
"""
import os
import shutil

from . import rf

from api import runtime_paths
from engine.utils.text_utils import safe_filename_component


MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
API_DIR = os.path.dirname(MODULE_DIR)
REPO_ROOT = os.path.dirname(API_DIR)
DEFAULT_DOCS_DIR = os.path.join(API_DIR, "default_docs")
DEFAULT_AI_TA_DIR = os.path.join(DEFAULT_DOCS_DIR, "AI Authoring")


def _write_text_if_missing(path, text):
    """Seed a file once and preserve teacher edits on later runs."""
    if os.path.exists(path):
        return False
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return True


def _copy_tree_if_missing(source_dir, dest_dir):
    """Seed every file under source_dir into dest_dir, preserving teacher edits."""
    written = []
    if not os.path.isdir(source_dir):
        return written
    for root, _, files in os.walk(source_dir):
        rel_dir = os.path.relpath(root, source_dir)
        target_root = dest_dir if rel_dir == "." else os.path.join(dest_dir, rel_dir)
        os.makedirs(target_root, exist_ok=True)
        for name in files:
            src = os.path.join(root, name)
            dest = os.path.join(target_root, name)
            if os.path.exists(dest):
                continue
            shutil.copy2(src, dest)
            written.append(dest)
    return written


def _sanitize_filename(text):
    return safe_filename_component(text, fallback="Rubric")


def _make_rubric_score_text(data):
    return rf.scoring_prompt(data).rstrip() + "\n"


def build_library(target_dir, rubric_folders=None):
    """Seed the AI Authoring library, then add one scoring skill per current rubric."""
    if rubric_folders is None:
        rubric_folders = runtime_paths.rubric_folders()
    os.makedirs(target_dir, exist_ok=True)
    written = _copy_tree_if_missing(DEFAULT_AI_TA_DIR, target_dir)

    for folder in rubric_folders:
        if not os.path.isdir(folder):
            continue
        for path in sorted(os.listdir(folder)):
            if not path.lower().endswith(".txt"):
                continue
            full_path = os.path.join(folder, path)
            data, problems = rf.parse_file(full_path)
            if data is None or problems:
                continue
            safe_title = _sanitize_filename(str(data.get("title", "Rubric")))
            filename = f"Score with - {safe_title}.txt"
            out_path = os.path.join(target_dir, filename)
            _write_text_if_missing(out_path, _make_rubric_score_text(data))
            written.append(out_path)

    return written
