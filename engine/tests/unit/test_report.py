"""Tests for the staged validation report (engine/validation/report.py)."""

from engine.core.quiz import Quiz
from engine.core.questions import MCQuestion, MCChoice
from engine.validation.report import build_validation_stages


def _mc(prompt, triples, ident=None):
    """triples: list of (text, correct) tuples."""
    return MCQuestion(
        qtype="MC",
        prompt=prompt,
        render_mode="executable",
        choices=[MCChoice(text=t, correct=c) for t, c in triples],
        forced_ident=ident,
    )


def _rats(item_id, n):
    """A complete per-choice rationale entry with n non-empty choice rationales."""
    return {
        "item_id": item_id,
        "choices": [
            {"id": chr(65 + i), "correct": i == 0, "rationale": f"because {i}"}
            for i in range(n)
        ],
    }


def _stage(stages, stage_id):
    return next(s for s in stages if s["id"] == stage_id)


def test_clean_quiz_all_stages_pass():
    # Correct answer is always the MIDDLE length (no length bias), and every MC
    # has complete per-choice rationales.
    quiz = Quiz(
        title="T",
        questions=[
            _mc("Q1?", [("aaaa", False), ("bb", False), ("ccc", True)], "q1"),
            _mc("Q2?", [("dddd", False), ("ee", False), ("fff", True)], "q2"),
            _mc("Q3?", [("gggg", False), ("hh", False), ("iii", True)], "q3"),
        ],
        rationales=[_rats("q1", 3), _rats("q2", 3), _rats("q3", 3)],
    )
    stages = build_validation_stages(quiz)
    assert {s["id"] for s in stages} == {
        "question_fields", "points_balance", "answer_lengths", "rationales",
    }
    assert all(s["status"] == "pass" for s in stages)


def test_missing_rationales_fails_that_stage_only():
    quiz = Quiz(
        title="T",
        questions=[
            _mc("Q1?", [("aaaa", False), ("bb", False), ("ccc", True)], "q1"),
            _mc("Q2?", [("dddd", False), ("ee", False), ("fff", True)], "q2"),
            _mc("Q3?", [("gggg", False), ("hh", False), ("iii", True)], "q3"),
        ],
        # no rationales
    )
    stages = build_validation_stages(quiz)
    assert _stage(stages, "question_fields")["status"] == "pass"
    assert _stage(stages, "answer_lengths")["status"] == "pass"
    assert _stage(stages, "rationales")["status"] == "fail"


def test_runs_all_stages_even_when_fields_fail():
    # MC with zero correct choices -> question_fields fails, but the other
    # stages must STILL run (run-all, no short-circuit).
    quiz = Quiz(title="T", questions=[_mc("Q1?", [("a", False), ("b", False)], "q1")])
    stages = build_validation_stages(quiz)
    assert _stage(stages, "question_fields")["status"] == "fail"
    assert _stage(stages, "points_balance")["status"] in {"pass", "fail"}
    assert _stage(stages, "answer_lengths")["status"] in {"pass", "fail"}
    assert _stage(stages, "rationales")["status"] in {"pass", "fail"}


def test_length_bias_flagged():
    # Correct answer is always the LONGEST -> length bias fail.
    quiz = Quiz(
        title="T",
        questions=[
            _mc("Q1?", [("a", False), ("bb", False), ("cccccccc", True)], "q1"),
            _mc("Q2?", [("d", False), ("ee", False), ("ffffffff", True)], "q2"),
            _mc("Q3?", [("g", False), ("hh", False), ("iiiiiiii", True)], "q3"),
        ],
        rationales=[_rats("q1", 3), _rats("q2", 3), _rats("q3", 3)],
    )
    stages = build_validation_stages(quiz)
    assert _stage(stages, "question_fields")["status"] == "pass"
    assert _stage(stages, "answer_lengths")["status"] == "fail"


def test_does_not_mutate_input():
    quiz = Quiz(title="T", questions=[_mc("Q1?", [("a", True), ("b", False)], "q1")])
    before = len(quiz.questions)
    build_validation_stages(quiz)
    assert len(quiz.questions) == before
