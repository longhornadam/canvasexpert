import json

import pytest

from ..parser import parse_news_json
from ..packager import package_quiz


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

def _build_payload(**overrides):
    """Base payload using the per-choice rationale format."""
    base = {
        "version": "3.0-json",
        "title": "Sample",
        "items": [
            {
                "id": "stim1",
                "type": "STIMULUS",
                "prompt": "Context block",
                "points": 10,  # should be stripped by parser
            },
            {
                "id": "q1",
                "type": "MC",
                "prompt": "Prompt?",
                "choices": [
                    {"id": "A", "text": "A", "correct": True},
                    {"id": "B", "text": "B", "correct": False},
                ],
            },
            {
                "id": "end1",
                "type": "STIMULUS_END",
                "prompt": "",
                "points": 5,  # should be stripped by parser
            },
        ],
        "rationales": [
            {
                "item_id": "q1",
                "choices": [
                    {"id": "A", "correct": True,  "rationale": "A is correct because it satisfies the condition."},
                    {"id": "B", "correct": False, "rationale": "B does not satisfy the condition."},
                ],
            },
        ],
    }
    base.update(overrides)
    return base


def _wrap(payload: dict) -> str:
    return f"<QUIZFORGE_JSON>{json.dumps(payload)}</QUIZFORGE_JSON>"


# ---------------------------------------------------------------------------
# Existing core behaviour tests (fixed imports + fixture)
# ---------------------------------------------------------------------------

def test_parse_handles_chatty_wrapping_and_strips_points_from_stimulus():
    text = f"Hello!\n<QUIZFORGE_JSON>\n{json.dumps(_build_payload())}\n</QUIZFORGE_JSON>\nThanks!"
    quiz = parse_news_json(text)

    assert quiz.version == "3.0-json"
    assert quiz.title == "Sample"
    assert len(quiz.items) == 3
    assert "points" not in quiz.items[0]  # STIMULUS stripped
    assert "points" not in quiz.items[2]  # STIMULUS_END stripped


def test_packager_filters_rationales_for_structural_items_only():
    payload = parse_news_json(_wrap(_build_payload()))
    packaged = package_quiz(payload)

    assert len(packaged.rationales) == 1
    assert packaged.rationales[0].item_id == "q1"
    assert packaged.items[0]["type"] == "STIMULUS"
    assert packaged.items[1]["type"] == "MC"


def test_metadata_passes_through_untouched():
    payload = _build_payload(
        metadata={"extensions": {"world": {"layout": "corridor", "q_per_room": 1}}},
    )
    payload["items"][1]["metadata"] = {"foo": "bar", "nested": {"hint": "keep"}}
    quiz = parse_news_json(_wrap(payload))
    assert quiz.metadata["extensions"]["world"]["layout"] == "corridor"
    assert quiz.items[1]["metadata"]["nested"]["hint"] == "keep"


def test_missing_tags_raises():
    with pytest.raises(ValueError):
        parse_news_json("No tags here")


# ---------------------------------------------------------------------------
# Per-choice rationale format
# ---------------------------------------------------------------------------

def _per_choice_payload():
    """Payload using the per-choice rationale format."""
    return {
        "version": "3.0-json",
        "title": "Per-Choice Test",
        "items": [
            {
                "id": "q1",
                "type": "MC",
                "prompt": "What does an arrow labeled 'Yes' represent in a flowchart?",
                "choices": [
                    {"id": "A", "text": "The path taken when the decision is Yes", "correct": True},
                    {"id": "B", "text": "The value stored in a variable", "correct": False},
                    {"id": "C", "text": "The number of loop iterations", "correct": False},
                    {"id": "D", "text": "The data type of the result", "correct": False},
                ],
            }
        ],
        "rationales": [
            {
                "item_id": "q1",
                "choices": [
                    {"id": "A", "correct": True,  "rationale": "Arrows show program flow; 'Yes' marks the path when the decision is true."},
                    {"id": "B", "correct": False, "rationale": "Variables store data values; they are unrelated to arrows."},
                    {"id": "C", "correct": False, "rationale": "Loop counts are not shown by individual arrows."},
                    {"id": "D", "correct": False, "rationale": "Data types describe variable kinds, not arrow labels."},
                ],
            }
        ],
    }


def test_per_choice_rationale_parses_correctly():
    quiz = parse_news_json(_wrap(_per_choice_payload()))

    assert len(quiz.rationales) == 1
    entry = quiz.rationales[0]
    assert entry.item_id == "q1"
    assert entry.choices is not None
    assert len(entry.choices) == 4


def test_per_choice_correct_flag_preserved():
    quiz = parse_news_json(_wrap(_per_choice_payload()))
    choices = quiz.rationales[0].choices

    correct_choices = [c for c in choices if c.correct]
    incorrect_choices = [c for c in choices if not c.correct]
    assert len(correct_choices) == 1
    assert correct_choices[0].id == "A"
    assert len(incorrect_choices) == 3


def test_per_choice_rationale_text_preserved():
    quiz = parse_news_json(_wrap(_per_choice_payload()))
    choices_by_id = {c.id: c for c in quiz.rationales[0].choices}

    assert "program flow" in choices_by_id["A"].rationale
    assert "data values" in choices_by_id["B"].rationale


def test_per_choice_survives_packager_filter():
    quiz = parse_news_json(_wrap(_per_choice_payload()))
    packaged = package_quiz(quiz)

    assert len(packaged.rationales) == 1
    assert packaged.rationales[0].item_id == "q1"
    assert packaged.rationales[0].choices is not None


# ---------------------------------------------------------------------------
# Malformed / edge-case entries are silently skipped
# ---------------------------------------------------------------------------

def test_malformed_entries_skipped_gracefully():
    """Entries without a valid choices array are silently dropped; valid ones are kept."""
    payload = _build_payload(rationales=[
        None,                                        # not a dict
        {"item_id": "q1"},                          # no choices key
        {"rationale": "missing item_id"},           # no item_id
        {"item_id": "q1", "choices": "not-a-list"}, # choices not a list
        {"item_id": "q1", "choices": [              # malformed choice entries inside
            {"id": "A"},                            # missing correct + rationale
            {"id": "B", "correct": True, "rationale": "Valid entry inside bad list."},
        ]},
    ])
    quiz = parse_news_json(_wrap(payload))

    # choices list with one malformed + one valid → still produces an entry
    # everything else → skipped
    assert len(quiz.rationales) == 1
    entry = quiz.rationales[0]
    assert entry.choices is not None
    assert len(entry.choices) == 1
    assert entry.choices[0].id == "B"

