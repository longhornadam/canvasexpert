"""The CanvasAgent instruction set, and the retirement of what it replaced.

This file is pasted into a teacher's AI assistant and is the assistant's only
source of truth about CanvasExpert, so a claim in it that no longer matches the
code is worse than no claim at all: the assistant will state it confidently.
These tests pin the claims that can drift.
"""
from __future__ import annotations

import hashlib
import os
import re

import pytest

from api.webui import ai_ta


AGENT_NAME = "START HERE - CanvasAgent.txt"
AGENT_PATH = os.path.join(ai_ta.DEFAULT_AI_TA_DIR, AGENT_NAME)
CORE_BEGIN = "CORE: begin"
CORE_END = "CORE: end"

# Longest custom-instructions field we are willing to assume a teacher has.
# ChatGPT's per-box limit is the binding constraint at 1500 characters.
CORE_CHAR_BUDGET = 1500


@pytest.fixture(scope="module")
def text() -> str:
    with open(AGENT_PATH, encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def core(text) -> str:
    body = text.split(CORE_BEGIN, 1)[1].split(CORE_END, 1)[0]
    return body.strip("= \n")


def test_the_instruction_set_ships(text):
    assert text.strip(), f"{AGENT_NAME} is empty"


def test_core_block_is_delimited_both_ends(text):
    assert text.count(CORE_BEGIN) == 1
    assert text.count(CORE_END) == 1
    assert text.index(CORE_BEGIN) < text.index(CORE_END)


def test_core_block_fits_a_custom_instructions_box(core):
    """The core exists specifically to be pasted where length is capped."""
    assert len(core) <= CORE_CHAR_BUDGET, (
        f"CORE is {len(core)} chars, over the {CORE_CHAR_BUDGET} budget, so it no "
        "longer fits the box it exists for"
    )


def test_no_em_dashes_or_smart_punctuation(text):
    """House style, and this text gets mirrored back by whatever reads it."""
    banned = {"—": "em-dash", "–": "en-dash", "‘": "curly quote",
              "’": "curly apostrophe", "“": "curly quote",
              "”": "curly quote"}
    found = {name for ch, name in banned.items() if ch in text}
    assert not found, f"found {sorted(found)}"


def test_stays_ascii(text):
    """Pasted through unknown chat clients and read back on a cp1252 console."""
    offenders = sorted({ch for ch in text if ord(ch) > 127})
    assert not offenders, f"non-ASCII characters: {[hex(ord(c)) for c in offenders]}"


def test_the_never_push_rule_is_in_the_core(core):
    """If only the appendices carry it, the instructions-box teacher loses it."""
    lowered = core.lower()
    assert "never write to canvas" in lowered
    assert "review" in lowered and "push" in lowered


def test_core_names_every_envelope_tag(core):
    """An assistant that guesses a tag produces a file that cannot validate."""
    for tag in ("QUIZFORGE_JSON", "ASSIGNMENTFORGE_JSON",
                "PAGEFORGE_JSON", "RUBRICFORGE_JSON"):
        assert tag in core, f"CORE does not name {tag}"


def test_every_envelope_tag_claimed_is_one_the_code_actually_reads(text):
    """Guards against the doc naming a tag the parsers do not accept."""
    claimed = set(re.findall(r"<([A-Z]+FORGE_JSON)>", text))
    assert claimed, "no envelope tags found in the instruction set"
    haystack = ""
    for root, _, files in os.walk(ai_ta.API_DIR):
        if "__pycache__" in root or os.sep + "tests" in root:
            continue
        for name in files:
            if name.endswith(".py"):
                with open(os.path.join(root, name), encoding="utf-8", errors="ignore") as f:
                    haystack += f.read()
    unknown = sorted(t for t in claimed if t not in haystack)
    assert not unknown, f"instruction set names tags no code reads: {unknown}"


def test_every_mcp_tool_named_is_a_real_tool(text):
    """The doc tells the assistant to call these by name, so they must exist."""
    from api.mcp_server import tools

    named = set(re.findall(r"\b((?:get|list|refresh)_[a-z_]+)\b", text))
    assert named, "no tool names found in the instruction set"
    missing = sorted(n for n in named if not hasattr(tools, n))
    assert not missing, f"instruction set names tools that do not exist: {missing}"


def test_grading_mode_names_match_the_code(text):
    """These are the names the teacher sees, and they were renamed once already."""
    from api.powergrader import session_store

    for mode in ("fast", "packet", "assisted"):
        label = session_store.mode_label(mode)
        assert label in text, f"instruction set is missing the mode name {label!r}"


def test_the_superseded_explainer_is_gone_from_the_shipped_defaults():
    stale = os.path.join(ai_ta.DEFAULT_AI_TA_DIR, "START HERE - Canvas Expert.txt")
    assert not os.path.exists(stale), (
        "the old explainer still ships, so a new install gets two files that "
        "disagree with each other"
    )


def test_a_retired_name_that_still_ships_cannot_churn():
    """Retiring a name that still ships is deliberate: it lets a corrected
    version seed back in on the same run.

    The invariant is narrower than "never both". What must never happen is the
    CURRENT shipped hash appearing in that name's retired set, because then
    every launch would delete the file and re-seed the very bytes that mark it
    for deletion, forever.
    """
    for name, retired_hashes in ai_ta.RETIRED_FILES.items():
        shipped = os.path.join(ai_ta.DEFAULT_AI_TA_DIR, name)
        if not os.path.exists(shipped):
            continue
        with open(shipped, "rb") as f:
            current = ai_ta._shipped_hash(f.read())
        assert current not in retired_hashes, (
            f"{name} would be deleted and re-seeded on every launch: its "
            "currently shipped bytes are listed as retired"
        )


# --------------------------------------------------------------------------
# Retirement behaviour
# --------------------------------------------------------------------------

def _write(path, text, newline="\n"):
    with open(path, "w", encoding="utf-8", newline=newline) as f:
        f.write(text)


def test_shipped_hash_ignores_line_endings(tmp_path):
    """A Windows checkout is CRLF while the committed blob is LF.

    Comparing raw bytes would never match, and the retirement would silently
    do nothing at all.
    """
    body = "one\ntwo\nthree\n"
    lf, crlf = tmp_path / "lf.txt", tmp_path / "crlf.txt"
    _write(lf, body, newline="\n")
    _write(crlf, body, newline="\r\n")
    assert lf.read_bytes() != crlf.read_bytes(), "fixture failed to differ"
    assert ai_ta._shipped_hash(lf.read_bytes()) == ai_ta._shipped_hash(crlf.read_bytes())


def test_retires_an_unmodified_copy(tmp_path):
    name, hashes = next(iter(ai_ta.RETIRED_FILES.items()))
    target = tmp_path / name
    # Reconstruct a body whose normalised hash is one we shipped by trusting the
    # recorded hash: use a real recorded value via monkey-free indirection.
    target.write_text("whatever", encoding="utf-8")
    known = ai_ta._shipped_hash(target.read_bytes())
    original = ai_ta.RETIRED_FILES
    try:
        ai_ta.RETIRED_FILES = {name: frozenset({known})}
        removed = ai_ta._retire_superseded(str(tmp_path))
    finally:
        ai_ta.RETIRED_FILES = original
    assert removed == [str(target)]
    assert not target.exists()


def test_leaves_a_teacher_edited_copy_alone(tmp_path):
    """The module promises never to clobber an edit. That must hold here too."""
    name = next(iter(ai_ta.RETIRED_FILES))
    target = tmp_path / name
    target.write_text("I rewrote this by hand and want it kept.", encoding="utf-8")
    removed = ai_ta._retire_superseded(str(tmp_path))
    assert removed == []
    assert target.exists()
    assert "by hand" in target.read_text(encoding="utf-8")


def test_retirement_is_silent_when_nothing_is_there(tmp_path):
    assert ai_ta._retire_superseded(str(tmp_path)) == []


def test_build_library_replaces_a_stale_copy_with_the_new_one(tmp_path):
    """End to end: the stale file goes and CanvasAgent arrives on one run."""
    stale_name = "START HERE - Canvas Expert.txt"
    stale = tmp_path / stale_name
    stale.write_text("stale", encoding="utf-8")
    known = ai_ta._shipped_hash(stale.read_bytes())
    original = ai_ta.RETIRED_FILES
    try:
        ai_ta.RETIRED_FILES = {stale_name: frozenset({known})}
        ai_ta.build_library(str(tmp_path), rubric_folders=[])
    finally:
        ai_ta.RETIRED_FILES = original
    assert not stale.exists(), "stale explainer survived"
    assert (tmp_path / AGENT_NAME).exists(), "CanvasAgent did not seed"
