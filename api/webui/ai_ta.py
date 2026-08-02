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
import hashlib
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


# Seeded files that a newer version replaces, mapped to every version of them
# we previously shipped.
#
# Both seeding helpers below skip a path that already exists, which is a
# deliberate promise to teachers who hand-edit these files. The side effect is
# that new contents never reach anyone who already has the file: they keep the
# stale copy. Deleting the stale copy first, so the current one seeds back in
# on the same run, is what actually updates them. A copy is only deleted when
# it still hashes to something we shipped, so a hand-edited file survives.
#
# This covers two cases with one mechanism:
#   * a rename, where the old name is listed and no longer ships
#   * a content update under the same name, where the name still ships and its
#     PREVIOUS hashes are listed
#
# Maintenance: when the text of a listed file changes, append the hash of the
# version being replaced. Get it with
#   git log --format=%H -- <path>
#   git show <rev>:<path> | sha256sum      (normalise CRLF to LF first)
# Listing the CURRENT shipped hash would delete and re-seed forever, which
# test_a_retired_name_that_still_ships_cannot_churn guards against.
RETIRED_FILES = {
    # Superseded by "START HERE - CanvasAgent.txt".
    "START HERE - Canvas Expert.txt": frozenset({
        "d7b59318f61d733380349846b948858a98ad06aed969ba15f2b8eeceea5d6eed",
    }),
    # Indexed the file above, so an unedited copy is stale the moment it goes.
    "About This Folder.txt": frozenset({
        "c3d90d2d29fd36ac9b3fecbc8982b9681d967a409fcda69c3d4d65d9e70e63b6",
        "00a7c1d978e5d02effde0f4b6d0a96d7d131ca324372eea641be2ee1cd247115",
    }),
    # Same-name updates. Teachers are told to hand this file to an AI, so a
    # stale copy answers setup questions wrongly rather than harmlessly.
    "START HERE - CanvasAgent.txt": frozenset({
        # First release, before the procedure-first rewrite.
        "66fb445401ff147e03b727d01d70e08f8337563f94d954ef6ac6fae9dfa0706b",
        # Procedure-first rewrite, before Appendix A on installing and running.
        "e5e4023c419e14de58339f32c3b6da5bafd81528aae91d41477640c5f27b21b6",
        # Before the scoring packet MCP tools were described.
        "94788ae4a8c063cd2e60f234e51a3f902e8fed8282b10caba80121135c8fb80b",
        # Before Panels and the Panel theme tools were described.
        "52f9755e202e51072cb687df1a0d1fa6b85d468dd371d7f8c30bd73e4c3656fe",
    }),
}


def _shipped_hash(raw):
    """Hash with line endings normalised.

    A Windows checkout stores these files CRLF while the committed blob is LF,
    so the same shipped text has two different raw byte hashes. Comparing
    without normalising would never match and would quietly retire nothing.
    """
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def _retire_superseded(target_dir):
    """Delete superseded seeded files the teacher has not modified."""
    removed = []
    for name, shipped_hashes in RETIRED_FILES.items():
        path = os.path.join(target_dir, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "rb") as f:
                if _shipped_hash(f.read()) not in shipped_hashes:
                    continue
        except OSError:
            continue
        try:
            os.remove(path)
        except OSError:
            continue
        removed.append(path)
    return removed


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
    _retire_superseded(target_dir)
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
