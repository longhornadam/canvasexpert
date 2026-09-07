"""AI Authoring library builder: seeds a teacher's workspace with the paste-ready
MagicSchool / Copilot skill files that live at ``api/default_docs/AI Authoring/``.

That folder is the sole repository source for these files -- every "Author a ...",
START HERE, Reference, and MagicSchool Toolkit file there is already the exact
paste-ready text a teacher pastes into an AI assistant. This module never
regenerates that text; it only seeds it into a teacher's workspace (once, never
overwriting an edit).

It also sweeps unedited "Score with - ..." files left behind by the retired
per-rubric scoring-skill generator; see _sweep_retired_scoring_skills below.

Pure module: builds plain-text output files only. The web UI / server owns the
HTTP routes and startup hook.
"""
import hashlib
import json
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
        # Before the folder index named the retired display contract, schedule,
        # objectives, and writing guides.
        "b31f29b5a32c1c4efa23ed9c9a3e53f408cdc029cee8aa1b503c6f981205a409",
    }),
    # Retired classroom-display authoring contract; remove only unchanged copies.
    "Author a SmartDeck (SlideForge).txt": frozenset({
        "1ddbd8451ec340171c1c2194bb45e18f71cea16c1640bd3458d8eabe5d46753f",
        "e6fa8e82ce0132c400a91f754962d63ef0cf7b50f7d8284a94317e5d14dcfeab",
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
        # Before Appendix D described the local write tools and Appendix B added
        # School Calendar and Learning Objectives coverage.
        "2cb1a3c99d4d01f0158fe61ce4995a0d5bcdab360430f62ee8363d8a75aa5798",
        # Before "Automations" was renamed to "Routines" (feature-freeze
        # hardening initiative, D2).
        "a7f4d921a378a5044680db39f679cf66eba3cef7369179d5056cc99139c246e6",
        # Before the 2026-08-06 Appendix D disclosure fix for the one explicit
        # digest-protected MCP Canvas-group write.
        "c8a48dea97670303c973422218bebaf2b65f87e64691a71dc647891ab71f9978",
        # Before Appendix A described the app's private Python environment and
        # Appendix D described resolving a shared section name by section_id.
        "83d68d6cdb03eb4dbe009eceefec41a89f64447e8b1c6023502a9d887eecba2a",
        # Before the classroom display and its Panel theme tools were removed.
        "3f2e05954005949ba2116bb71ccc72f776b10b704d8128bf676cb419a3cf34fc",
        # Before the CORE write rule was corrected: it had claimed the
        # assistant never writes to Canvas at all, which the bounded New Quiz
        # and SIS bridge operations contradict.
        "19918f641efaab0447e756361de3eed45c065b4974398726568339592bf07898",
        # Same correction, one release earlier: the version that shipped
        # between the display removal and the guide scoping. A workspace
        # seeded in between holds this one, and an unlisted hash reads as
        # "the teacher edited it", so without this the fix never lands.
        "c01072b33ce1e844244abebad374201c645ba6a72d24f782204cacfce696d07e",
        # Before the CORE write rule stopped denying the direct-write path.
        # Staging is the default, and a teacher who asks for a direct write
        # gets one; "never write to Canvas on your own" only softened the
        # denial instead of correcting it.
        "cfbcb2e652948cb18ba2ebd1d22e6ffbba79757a9c50a3d4e0f44bd14286e962",
        # Before the direct write stopped being gated behind a second ask.
        # The teacher asking for the write is the authorization.
        "1da24d0600b3c50fd7ef78dadc22327dfdd4c38a2cca2d2adde2d2a36000d36a",
        # Before CORE named the scoring write path. It had said a teacher
        # could have "scores" written straight to Canvas, which promises
        # generic grade posting; only New Quiz item scores can go.
        "183bac2d77afc38c98c79def8cada375f7c9dea1afdb9fc15eae80adf54da931",
    }),
    # Named the removed classroom display alongside Calendar.
    "Author a Class Schedule.txt": frozenset({
        "b65df7567b0b26b29aa23c4c58ea4432767d8a7a05fb7987059fda9a30536275",
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


def _legacy_rubric_score_text(data):
    """Reproduce the text the retired per-rubric scoring generator used to write.

    build_library used to add one "Score with - <rubric>.txt" file per rubric on
    file, built from rf.scoring_prompt. That generator is retired: it told a
    teacher to paste real student writing into a chat with no pseudonymization,
    and its output carried no pseudonym/item_id, so it could never be imported
    into a PowerGrader session. rf.scoring_prompt went with it, since nothing
    else called it.

    This is a frozen, private duplicate of what that function produced, kept
    only so _sweep_retired_scoring_skills can recognize a file an earlier
    rebuild wrote and nobody has touched since. Do not evolve this to track
    rf.py or rubric-shape changes -- doing so would break the match against
    files already sitting in a teacher's workspace, which is the only reason
    it still exists.
    """
    def _text(value):
        return str(value or "").strip()

    total = data.get("total_points")
    lines = [
        "You are an experienced teacher scoring student writing with the rubric below.",
        "Score each criterion independently and honestly — a response can be excellent in",
        "one criterion and weak in another. Use the full range. Quote briefly from the",
        "student's work to justify every score.",
        "",
        f"RUBRIC: {_text(data.get('title'))} ({total} points)",
        "",
    ]

    for i, criterion in enumerate(data.get("criteria") or []):
        lines.append(f"CRITERION {i + 1}: {_text(criterion.get('name'))} — {_text(criterion.get('points'))} points")
        cq = _text(criterion.get("core_question"))
        if cq:
            lines.append(f"Core question: {cq}")
        for rating in criterion.get("ratings") or []:
            range_min = rating.get("range_min")
            band = f" (band {range_min}-{rating.get('points')})" if range_min is not None else ""
            lines.append(f"  [{rating.get('points')} pts{band}] {_text(rating.get('label'))}: {_text(rating.get('description'))}")
        lines.append("")

    guidance = data.get("scoring_guidance") or {}
    if guidance:
        lines.append("SCORING PRINCIPLES")
        for item in guidance.get("design_principles") or []:
            lines.append(f"- {_text(item)}")
        for item in guidance.get("consistency_tips") or []:
            lines.append(f"- {_text(item)}")
        scr_scaling = _text(guidance.get("scr_scaling"))
        if scr_scaling:
            lines.append(scr_scaling)
        lines.append("")

        output_template = guidance.get("output_template")
        if output_template is not None:
            lines.append("Return your evaluation as JSON in exactly this structure, then a short")
            lines.append("plain-English summary a student could read:")
            lines.append(json.dumps(output_template, indent=2))
            lines.append("")

    lines.append("I will paste one student response at a time. Wait for it.")
    return "\n".join(lines).rstrip() + "\n"


def _sweep_retired_scoring_skills(target_dir, rubric_folders):
    """Delete a "Score with - ..." file only if it still matches what the
    retired generator would produce from the matching rubric today.

    RETIRED_FILES above cannot reach these files: it is keyed on an exact
    filename plus a frozenset of shipped-content hashes, and here both the
    filename and the contents come from each teacher's own rubric titles, not
    from anything this repo ships. There is no shippable name list and no
    shippable hash.

    What we do have is the rubric itself, so this recomputes the old output
    from the rubric currently on file and deletes the on-disk file only when
    it still matches byte for byte. A file whose rubric was edited, renamed, or
    removed since generation no longer matches and is left alone, and so is a
    file the teacher edited directly -- this only ever deletes what it can
    prove is an untouched leftover.
    """
    removed = []
    try:
        on_disk = {
            name for name in os.listdir(target_dir)
            if name.startswith("Score with - ") and name.lower().endswith(".txt")
        }
    except OSError:
        return removed
    if not on_disk:
        return removed

    for folder in rubric_folders:
        if not os.path.isdir(folder):
            continue
        for path in sorted(os.listdir(folder)):
            if not path.lower().endswith(".txt"):
                continue
            data, problems = rf.parse_file(os.path.join(folder, path))
            if data is None or problems:
                continue
            safe_title = _sanitize_filename(str(data.get("title", "Rubric")))
            filename = f"Score with - {safe_title}.txt"
            if filename not in on_disk:
                continue
            out_path = os.path.join(target_dir, filename)
            try:
                with open(out_path, "rb") as f:
                    current_raw = f.read()
            except OSError:
                continue
            expected_raw = _legacy_rubric_score_text(data).encode("utf-8")
            if _shipped_hash(current_raw) != _shipped_hash(expected_raw):
                continue
            try:
                os.remove(out_path)
            except OSError:
                continue
            removed.append(out_path)
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


def build_library(target_dir, rubric_folders=None):
    """Seed the AI Authoring library, then retire files superseded by newer ones."""
    if rubric_folders is None:
        rubric_folders = runtime_paths.rubric_folders()
    os.makedirs(target_dir, exist_ok=True)
    _retire_superseded(target_dir)
    _sweep_retired_scoring_skills(target_dir, rubric_folders)
    return _copy_tree_if_missing(DEFAULT_AI_TA_DIR, target_dir)
