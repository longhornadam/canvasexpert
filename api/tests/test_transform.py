"""Example test for the essay/file-upload feedback transport in api/transform.py.

Unit C of RATIONALE-BATCH-BRIEF.md: ESSAY and FILEUPLOAD items reuse the existing
single-rationale field to carry a student-facing exemplar, transported to Canvas
through the same "feedback" key the other scored types already use. This is the
one documentation example per AGENTS.md's test taxonomy: it shows the happy path
(an authored exemplar reaches the built item as neutral feedback) and confirms
an item with no exemplar is unchanged (_neutral_feedback returns {} when there
is no rationale, so no feedback content is added).

Offline: builds a plain dict through t_essay directly, no network, no Canvas.
"""
from api.transform import t_essay


def test_essay_rationale_becomes_neutral_feedback_exemplar():
    exemplar_text = "A cell is the basic unit of life. Every living thing is made of cells."
    item_with_exemplar = {
        "id": "Q1",
        "type": "ESSAY",
        "prompt": "In your own words, explain what a cell is.",
        "_rationale": {"item_id": "Q1", "rationale": exemplar_text},
    }

    built = t_essay(item_with_exemplar, 1)
    feedback = built["item"]["entry"]["feedback"]

    assert feedback == {"neutral": f"<p>{exemplar_text}</p>"}

    item_without_exemplar = {
        "id": "Q2",
        "type": "ESSAY",
        "prompt": "In your own words, explain what a cell is.",
    }

    built_bare = t_essay(item_without_exemplar, 2)

    assert built_bare["item"]["entry"]["feedback"] == {}
