"""Slice-1 target test for the paper render layer — `to_printdoc(Quiz)`.

This is the green checkmark the Toyota implementer builds toward (see
`docs/handoffs/paper-render-layer-slice1.md`). It exercises ONLY the pure-Python
adapter: it imports `engine.rendering.physical.printdoc` and
`engine.rendering.physical.quiz_adapter` and nothing else — no WeasyPrint, no
Pandoc — so the suite never depends on native libs.

EXPECTED STATE until slice 1 lands: this module fails to import (the two modules
don't exist yet). That collection error IS the starting "red." Implement
`printdoc.py` + `quiz_adapter.py` to the schema in the handoff and these
assertions turn green. Do not weaken an assertion to make it pass — if one
genuinely doesn't fit the chosen schema, fix it in the handoff + here together,
not silently.

The adapter contract under test (from the handoff):
  - PrintDoc(title, instructions, blocks, answer_key)
  - blocks is an ordered list; a Stimulus appears once before its questions;
    Question blocks carry a 1-based `number` that counts SCORABLE questions only
    (Stimulus markers are not numbered and are not in answer_key).
  - MC/MA payload: choices=[Choice(letter, html)], two_column:bool
    (two_column = every choice text shorter than MC_TWO_COLUMN_THRESHOLD).
  - answer_key: rows=[KeyRow(number, answer, points)], total
"""

import pytest

# Import the live domain model (this part already exists).
from engine.core.quiz import Quiz
from engine.core.questions import (
    MCQuestion,
    MCChoice,
    TFQuestion,
    StimulusItem,
    StimulusEnd,
)
from engine.rendering.physical.styles.default_styles import MC_TWO_COLUMN_THRESHOLD

# Import the slice-1 deliverables. Until they exist, collection fails here —
# that is the intended starting state.
from engine.rendering.physical.printdoc import PrintDoc, Stimulus, Question
from engine.rendering.physical.quiz_adapter import to_printdoc


def _sample_quiz() -> Quiz:
    """A small but representative quiz:

    1. A prose stimulus group containing ONE short-choice MC (two-column path).
    2. A standalone MC with one very long choice (single-column path).
    3. A standalone True/False.

    Stimulus points are pinned to 0 (as the runtime point-calculator does), so
    the scorable total is a clean 30.0.
    """
    long_choice = "This choice is deliberately written to exceed fifty characters in length."
    assert len(long_choice) > MC_TWO_COLUMN_THRESHOLD  # guard the test's own premise

    return Quiz(
        title="Sample Paper Quiz",
        instructions="Read each question carefully.",
        questions=[
            # --- stimulus group ---
            StimulusItem(
                qtype="STIMULUS",
                prompt="<p>Two roads diverged in a yellow wood.</p>",
                points=0,
                title="The Road Not Taken",
                author="Robert Frost",
            ),
            MCQuestion(
                qtype="MC",
                prompt="What color is the wood?",
                points=10,
                choices=[
                    MCChoice(text="Yellow", correct=True),   # A (correct)
                    MCChoice(text="Green", correct=False),    # B
                    MCChoice(text="Red", correct=False),      # C
                    MCChoice(text="Blue", correct=False),     # D
                ],
            ),
            StimulusEnd(qtype="STIMULUS_END", prompt="", points=0),
            # --- standalone long-choice MC (single column) ---
            MCQuestion(
                qtype="MC",
                prompt="Which statement is correct?",
                points=10,
                choices=[
                    MCChoice(text="Short A", correct=False),  # A
                    MCChoice(text="Short B", correct=False),  # B
                    MCChoice(text=long_choice, correct=True),  # C (correct)
                ],
            ),
            # --- standalone True/False ---
            TFQuestion(
                qtype="TF",
                prompt="Frost wrote this poem.",
                points=10,
                answer_true=True,
            ),
        ],
    )


@pytest.fixture
def printdoc() -> PrintDoc:
    return to_printdoc(_sample_quiz())


def test_top_level_metadata(printdoc):
    assert printdoc.title == "Sample Paper Quiz"
    assert printdoc.instructions == "Read each question carefully."


def test_block_order_and_question_numbering(printdoc):
    """Stimulus is its own block before its question; numbering counts scorable
    questions only (1, 2, 3) and never the stimulus markers."""
    blocks = printdoc.blocks

    # First block is the stimulus; the StimulusEnd marker is NOT a block.
    assert isinstance(blocks[0], Stimulus)

    questions = [b for b in blocks if isinstance(b, Question)]
    assert [q.number for q in questions] == [1, 2, 3]
    assert [q.qtype for q in questions] == ["MC", "MC", "TF"]

    # The stimulus precedes its (first) question in document order.
    assert blocks.index(blocks[0]) < blocks.index(questions[0])


def test_stimulus_fields(printdoc):
    stim = next(b for b in printdoc.blocks if isinstance(b, Stimulus))
    assert stim.title == "The Road Not Taken"
    assert stim.author == "Robert Frost"
    assert stim.fmt == "text"          # prose, not poetry
    assert stim.body_html.strip()      # non-empty rendered body


def test_mc_two_column_flag_and_choice_letters(printdoc):
    questions = [b for b in printdoc.blocks if isinstance(b, Question)]
    short_mc, long_mc = questions[0], questions[1]

    # Short-choice MC → two-column; long-choice MC → single column.
    assert short_mc.payload.two_column is True
    assert long_mc.payload.two_column is False

    # Choice letters are assigned A, B, C, ... by index.
    assert [c.letter for c in short_mc.payload.choices] == ["A", "B", "C", "D"]
    assert [c.letter for c in long_mc.payload.choices] == ["A", "B", "C"]


def test_answer_key_rows_and_total(printdoc):
    key = printdoc.answer_key
    assert key is not None

    # One row per scorable question, numbered to match.
    assert [r.number for r in key.rows] == [1, 2, 3]

    # Correct answers: MC→letter, TF→"True".
    assert key.rows[0].answer == "A"      # "Yellow" was correct
    assert key.rows[1].answer == "C"      # the long choice was correct
    assert key.rows[2].answer == "True"

    # Points per row and grand total (stimulus contributes 0).
    assert all(float(r.points) == 10.0 for r in key.rows)
    assert float(key.total) == 30.0
