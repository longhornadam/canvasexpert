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


def test_per_choice_feedback_reads_as_sentences_not_a_because_clause():
    """A two-sentence rationale must not be spliced after "because".

    The rationale shape is a concept sentence followed by a sentence tying it to
    this choice, so the verdict has to stand as its own sentence. Splicing gives
    "is correct because Each HTML element...", which is not English.
    """
    from api.transform import t_mc

    concept = "Each HTML element has one specific job."
    item = {
        "id": "q1",
        "type": "MC",
        "prompt": "<p>Which element links to another page?</p>",
        "choices": [
            {"id": "A", "text": "anchor", "correct": True},
            {"id": "B", "text": "paragraph", "correct": False},
        ],
        "_rationale": {
            "item_id": "q1",
            "choices": [
                {"id": "A", "correct": True, "rationale": f"{concept} The anchor links, so it fits."},
                {"id": "B", "correct": False, "rationale": f"{concept} A paragraph holds text, so it does not fit."},
            ],
        },
    }

    feedback = " ".join(t_mc(item, 1)["item"]["entry"]["answer_feedback"].values())

    assert "because" not in feedback
    assert '"anchor" is correct.' in feedback
    assert '"paragraph" is wrong.' in feedback
    assert concept in feedback
