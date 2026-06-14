"""Tests for rationale coverage across all scorable question types."""

from engine.core.quiz import Quiz
from engine.core.questions import MCQuestion, MCChoice, TFQuestion, EssayQuestion
from engine.validation.rules.rationale_rules import check_rationale_coverage


def _mc(ident, n_choices):
    return MCQuestion(
        qtype="MC",
        prompt="Q?",
        render_mode="executable",
        choices=[MCChoice(text=f"c{i}", correct=(i == 0)) for i in range(n_choices)],
        forced_ident=ident,
    )


def _per_choice(item_id, rationale_texts):
    return {
        "item_id": item_id,
        "choices": [
            {"id": chr(65 + i), "correct": i == 0, "rationale": t}
            for i, t in enumerate(rationale_texts)
        ],
    }


def _single(item_id, text):
    return {"item_id": item_id, "rationale": text}


# --- MC / MA per-choice ---

def test_mc_full_coverage_passes():
    quiz = Quiz(title="T", questions=[_mc("q1", 4)],
                rationales=[_per_choice("q1", ["a", "b", "c", "d"])])
    assert check_rationale_coverage(quiz) == []


def test_mc_missing_entry_fails():
    quiz = Quiz(title="T", questions=[_mc("q1", 4)], rationales=[])
    errors = check_rationale_coverage(quiz)
    assert "no per-choice rationales" in errors[0]


def test_mc_count_mismatch_fails():
    quiz = Quiz(title="T", questions=[_mc("q1", 4)],
                rationales=[_per_choice("q1", ["a", "b", "c"])])
    assert "4 answer choices but 3" in check_rationale_coverage(quiz)[0]


def test_mc_empty_text_fails():
    quiz = Quiz(title="T", questions=[_mc("q1", 3)],
                rationales=[_per_choice("q1", ["a", "", "c"])])
    assert "empty for choice(s) 2" in check_rationale_coverage(quiz)[0]


# --- Single-rationale types ---

def _tf(ident):
    return TFQuestion(qtype="TF", prompt="Sky is blue?", render_mode="executable",
                      answer_true=True, forced_ident=ident)


def test_tf_with_single_rationale_passes():
    quiz = Quiz(title="T", questions=[_tf("tf1")],
                rationales=[_single("tf1", "True because the sky scatters blue light.")])
    assert check_rationale_coverage(quiz) == []


def test_tf_without_rationale_fails():
    quiz = Quiz(title="T", questions=[_tf("tf1")], rationales=[])
    errors = check_rationale_coverage(quiz)
    assert "needs a \"rationale\"" in errors[0]


# --- Essay model-answer guidance ---

def _essay(ident):
    return EssayQuestion(qtype="ESSAY", prompt="Discuss.", render_mode="executable",
                         forced_ident=ident)


def test_essay_with_model_answer_passes():
    quiz = Quiz(title="T", questions=[_essay("e1")],
                rationales=[_single("e1", "A strong response connects evidence to a claim.")])
    assert check_rationale_coverage(quiz) == []


def test_essay_without_guidance_fails():
    quiz = Quiz(title="T", questions=[_essay("e1")], rationales=[])
    errors = check_rationale_coverage(quiz)
    assert "strong response" in errors[0]


def test_missing_id_fails():
    quiz = Quiz(title="T", questions=[_mc(None, 3)], rationales=[])
    assert "needs a unique" in check_rationale_coverage(quiz)[0]
