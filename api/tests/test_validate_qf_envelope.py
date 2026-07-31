"""QuizForge envelope validation, at the level the Create page depends on.

The staged-drafts panel badges a draft "Valid" or "Needs fixes" purely from
``validate_qf.validate``, and only offers "Use this draft" for a valid one. So
anything this function waves through is something the teacher can push straight
to Canvas.
"""
from __future__ import annotations

import json
import textwrap

import pytest

from api import validate_qf


def _envelope(tmp_path, payload, name="draft.txt"):
    """Write ``payload`` inside a QUIZFORGE_JSON envelope and return the path."""
    body = payload if isinstance(payload, str) else json.dumps(payload)
    path = tmp_path / name
    path.write_text(
        "<QUIZFORGE_JSON>\n" + body + "\n</QUIZFORGE_JSON>\n",
        encoding="utf-8",
        newline="\n",
    )
    return str(path)


ONE_GOOD_MC = {
    "version": "3.0-json",
    "title": "Cell Transport Check",
    "items": [
        {
            "id": "mc1",
            "type": "MC",
            "prompt": "<p>Why does dye spread evenly through still water?</p>",
            "choices": [
                {"id": "A", "text": "Diffusion down a concentration gradient", "correct": True},
                {"id": "B", "text": "Osmosis across a selectively permeable membrane", "correct": False},
            ],
        }
    ],
    "rationales": [
        {
            "item_id": "mc1",
            "choices": [
                {"id": "A", "correct": True, "rationale": "Particles spread from higher to lower concentration."},
                {"id": "B", "correct": False, "rationale": "Osmosis needs a membrane, and there is none here."},
            ],
        }
    ],
}


def test_a_well_formed_quiz_passes(tmp_path):
    assert validate_qf.validate(_envelope(tmp_path, ONE_GOOD_MC), set()) == []


@pytest.mark.parametrize(
    "payload, description",
    [
        ({"version": "3.0-json", "items": []}, "items present but empty"),
        ({"version": "3.0-json"}, "items key absent entirely"),
        ({"version": "3.0-json", "items": [], "rationales": []}, "empty items with empty rationales"),
    ],
)
def test_a_quiz_with_no_questions_is_rejected(tmp_path, payload, description):
    """An empty draft satisfies every per-item rule by having nothing to check.

    Without an explicit guard it reported as valid, so the staged-drafts panel
    badged it "Valid" and offered to push a quiz with zero questions to Canvas.
    """
    problems = validate_qf.validate(_envelope(tmp_path, payload), set())
    assert problems, f"expected rejection for {description}"
    assert any("no questions" in p for p in problems), problems


def test_missing_envelope_is_rejected(tmp_path):
    path = tmp_path / "bare.txt"
    path.write_text(json.dumps(ONE_GOOD_MC), encoding="utf-8", newline="\n")
    problems = validate_qf.validate(str(path), set())
    assert any("envelope" in p for p in problems), problems


def test_invalid_json_is_rejected(tmp_path):
    problems = validate_qf.validate(_envelope(tmp_path, "{not json,,,}"), set())
    assert any("INVALID JSON" in p for p in problems), problems


def test_mc_without_a_correct_choice_is_rejected(tmp_path):
    payload = json.loads(json.dumps(ONE_GOOD_MC))
    for choice in payload["items"][0]["choices"]:
        choice["correct"] = False
    problems = validate_qf.validate(_envelope(tmp_path, payload), set())
    assert any("has 0 correct" in p for p in problems), problems


def test_scored_item_without_a_rationale_is_rejected(tmp_path):
    payload = json.loads(json.dumps(ONE_GOOD_MC))
    payload.pop("rationales")
    problems = validate_qf.validate(_envelope(tmp_path, payload), set())
    assert any("missing rationale" in p for p in problems), problems
