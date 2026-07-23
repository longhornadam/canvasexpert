"""Unit tests specifically for meta-answer detection in length bias validation.

Tests the standardized meta-answer system defined in Section 10 of the QuizForge contract
embedded in api/default_docs/AI Authoring/Author a Quiz (QuizForge).txt.
Only exact phrasings are recognized; variations are intentionally rejected to enforce
consistency across all quizzes.
"""

import pytest
from engine.validation.rules.fairness_rules import (
    _is_meta_answer, 
    check_length_bias, 
    META_ANSWERS,
    _suggest_meta_answer
)
from engine.core.quiz import Quiz
from engine.core.questions import MCQuestion, MCChoice


def test_standardized_phrasings_only():
    """Only exact standardized phrasings are recognized as meta-answers."""
    # These MUST be recognized
    assert _is_meta_answer("No change is needed")
    assert _is_meta_answer("All of the above")
    assert _is_meta_answer("None of the above")
    assert _is_meta_answer("Both A and B")
    assert _is_meta_answer("Neither is correct")
    
    # Whitespace handling
    assert _is_meta_answer("  No change is needed  ")  # Strips whitespace
    
    # Case sensitivity - exact match required
    assert not _is_meta_answer("NO CHANGE IS NEEDED")  # Wrong case
    assert not _is_meta_answer("no change is needed")  # Wrong case


def test_rejects_variations():
    """Non-standard variations are NOT recognized as meta-answers."""
    # These should NOT be recognized (enforce exact standardization)
    assert not _is_meta_answer("No changes are needed")  # Plural
    assert not _is_meta_answer("No change needed")  # Missing words
    assert not _is_meta_answer("No correction required")  # Different wording
    assert not _is_meta_answer("All three sentences equally support")  # Variation
    assert not _is_meta_answer("All are correct")  # Different phrasing
    assert not _is_meta_answer("None of the choices")  # Variation
    assert not _is_meta_answer("Both are correct")  # Missing label
    assert not _is_meta_answer("Neither are correct")  # Different phrasing


def test_content_answers_not_flagged():
    """Regular content answers are not detected as meta-answers."""
    assert not _is_meta_answer("Remove the comma")
    assert not _is_meta_answer("This is a normal answer")
    assert not _is_meta_answer("The answer is B")
    assert not _is_meta_answer("Change the punctuation")
    assert not _is_meta_answer("Insert a semicolon")


def test_meta_answer_set_completeness():
    """Verify the META_ANSWERS set contains all standardized phrasings."""
    expected = {
        "No change is needed",
        "All of the above",
        "None of the above",
        "Both A and B",
        "Both A and C",
        "Both A and D",
        "Both B and C",
        "Both B and D",
        "Both C and D",
        "Neither is correct",
    }
    assert META_ANSWERS == expected


def test_suggests_standard_for_variations():
    """Non-standard variations get helpful suggestions."""
    # Common variations for "No change is needed"
    assert _suggest_meta_answer("No changes are needed") == "No change is needed"
    assert _suggest_meta_answer("No change needed") == "No change is needed"
    assert _suggest_meta_answer("no correction required") == "No change is needed"  # case insensitive
    assert _suggest_meta_answer("NO CHANGES NEEDED") == "No change is needed"  # case insensitive
    
    # Common variations for "All of the above"
    assert _suggest_meta_answer("All are correct") == "All of the above"
    assert _suggest_meta_answer("All three choices") == "All of the above"
    assert _suggest_meta_answer("all of these") == "All of the above"
    
    # Common variations for "None of the above"
    assert _suggest_meta_answer("None are correct") == "None of the above"
    assert _suggest_meta_answer("None of the choices") == "None of the above"
    
    # Whitespace handling
    assert _suggest_meta_answer("  No changes are needed  ") == "No change is needed"
    
    # Should not suggest for regular content
    assert _suggest_meta_answer("Add a comma after the word") is None
    assert _suggest_meta_answer("Remove the semicolon") is None
    
    # Should not suggest for already-standard phrasings
    assert _suggest_meta_answer("No change is needed") is None  # Already standard
    assert _suggest_meta_answer("All of the above") is None  # Already standard


def test_length_bias_with_standardized_meta_answer():
    """When standardized meta-answer is correct, it's excluded from length comparison."""
    quiz = Quiz(
        title="Editing Quiz",
        questions=[
            # Q1: Standardized meta-answer (correct) vs longer distractor
            MCQuestion(
                qtype="MC",
                prompt="Q1",
                choices=[
                    MCChoice(text="No change is needed", correct=True),  # Standardized meta
                    MCChoice(text="Remove the comma after the long phrase here because it's incorrect", correct=False)
                ]
            ),
            # Q2: Same pattern
            MCQuestion(
                qtype="MC",
                prompt="Q2",
                choices=[
                    MCChoice(text="No change is needed", correct=True),  # Standardized meta
                    MCChoice(text="Insert a semicolon between the two independent clauses in the sentence", correct=False)
                ]
            ),
            # Q3: Same pattern
            MCQuestion(
                qtype="MC",
                prompt="Q3",
                choices=[
                    MCChoice(text="No change is needed", correct=True),  # Standardized meta
                    MCChoice(text="Replace the period with a comma and add the appropriate conjunction", correct=False)
                ]
            )
        ]
    )
    
    errors = check_length_bias(quiz)
    # Should have NO errors - meta-answers excluded, leaving only 1 substantive choice per question
    # Questions with < 2 substantive choices are skipped, so 0 questions analyzed
    assert len(errors) == 0


def test_length_bias_with_non_standardized_variation():
    """Non-standardized variations ARE NOT excluded and should trigger length bias."""
    quiz = Quiz(
        title="Test",
        questions=[
            MCQuestion(
                qtype="MC",
                prompt="Q1",
                choices=[
                    MCChoice(text="No changes are needed in this sentence", correct=True),  # NOT standardized (plural)
                    MCChoice(text="Remove comma", correct=False)
                ]
            ),
            MCQuestion(
                qtype="MC",
                prompt="Q2",
                choices=[
                    MCChoice(text="No change needed for this one", correct=True),  # NOT standardized (missing words)
                    MCChoice(text="Insert semicolon", correct=False)
                ]
            ),
            MCQuestion(
                qtype="MC",
                prompt="Q3",
                choices=[
                    MCChoice(text="No correction required here", correct=True),  # NOT standardized (different wording)
                    MCChoice(text="Replace period", correct=False)
                ]
            )
        ]
    )
    
    errors = check_length_bias(quiz)
    # Should FAIL - variations not excluded, so length comparison happens
    # All 3 questions have correct as longest (100% >= 60%)
    assert len(errors) > 0
    assert "Longest answer is correct" in errors[0]


def test_length_bias_with_standardized_meta_as_distractor():
    """When standardized meta-answer is a distractor, it's excluded from comparison."""
    quiz = Quiz(
        title="Test",
        questions=[
            # Correct is longest among substantive choices in all 3
            MCQuestion(
                qtype="MC",
                prompt="Q1",
                choices=[
                    MCChoice(text="This is the correct answer with more detail and explanation", correct=True),
                    MCChoice(text="Short", correct=False),
                    MCChoice(text="All of the above", correct=False)  # Standardized meta, excluded
                ]
            ),
            MCQuestion(
                qtype="MC",
                prompt="Q2",
                choices=[
                    MCChoice(text="Another detailed correct answer here with lots of content", correct=True),
                    MCChoice(text="Brief", correct=False),
                    MCChoice(text="None of the above", correct=False)  # Standardized meta, excluded
                ]
            ),
            MCQuestion(
                qtype="MC",
                prompt="Q3",
                choices=[
                    MCChoice(text="Yet another long correct answer with substantial detail", correct=True),
                    MCChoice(text="Tiny", correct=False),
                    MCChoice(text="No change is needed", correct=False)  # Standardized meta, excluded
                ]
            )
        ]
    )
    
    errors = check_length_bias(quiz)
    # Should FAIL - 100% of questions have longest correct (after excluding meta-answers)
    assert len(errors) > 0
    assert "Longest answer is correct in 100%" in errors[0]


def test_balanced_quiz_with_standardized_meta_answers():
    """Balanced quiz with standardized meta-answers should pass."""
    quiz = Quiz(
        title="Balanced",
        questions=[
            # Q1: Correct is LONGEST among substantive
            MCQuestion(
                qtype="MC",
                prompt="Q1",
                choices=[
                    MCChoice(text="This is definitely the correct and longest answer here", correct=True),
                    MCChoice(text="Short", correct=False),
                    MCChoice(text="All of the above", correct=False)  # Standardized meta
                ]
            ),
            # Q2: Correct is SHORTEST among substantive
            MCQuestion(
                qtype="MC",
                prompt="Q2",
                choices=[
                    MCChoice(text="Correct", correct=True),
                    MCChoice(text="This is a much longer incorrect distractor answer here", correct=False),
                    MCChoice(text="None of the above", correct=False)  # Standardized meta
                ]
            ),
            # Q3: Correct is IN THE MIDDLE
            MCQuestion(
                qtype="MC",
                prompt="Q3",
                choices=[
                    MCChoice(text="Medium correct answer", correct=True),
                    MCChoice(text="This is definitely longer than the correct answer provided", correct=False),
                    MCChoice(text="Tiny", correct=False),
                    MCChoice(text="No change is needed", correct=False)  # Standardized meta
                ]
            ),
            # Q4: Correct is IN THE MIDDLE again
            MCQuestion(
                qtype="MC",
                prompt="Q4",
                choices=[
                    MCChoice(text="Another medium answer", correct=True),
                    MCChoice(text="Short", correct=False),
                    MCChoice(text="This is the longest answer in this particular question here", correct=False),
                ]
            )
        ]
    )
    
    errors = check_length_bias(quiz)
    # 1/4 longest (25% < 60%), 1/4 shortest (25% < 60%) - should pass
    assert len(errors) == 0


def test_error_message_includes_suggestion():
    """When length bias is detected with variations, error includes helpful suggestion."""
    quiz = Quiz(
        title="Test",
        questions=[
            MCQuestion(
                qtype="MC",
                prompt="Q1",
                choices=[
                    MCChoice(text="No changes are needed in this sentence", correct=True),  # Variation
                    MCChoice(text="Remove comma", correct=False)
                ]
            ),
            MCQuestion(
                qtype="MC",
                prompt="Q2",
                choices=[
                    MCChoice(text="No change needed for this one", correct=True),  # Variation
                    MCChoice(text="Insert semicolon", correct=False)
                ]
            ),
            MCQuestion(
                qtype="MC",
                prompt="Q3",
                choices=[
                    MCChoice(text="No correction required here", correct=True),  # Variation
                    MCChoice(text="Replace period", correct=False)
                ]
            )
        ]
    )
    
    errors = check_length_bias(quiz)
    assert len(errors) > 0
    assert "Longest answer is correct" in errors[0]
    # Should include helpful suggestion
    assert "💡 Tip:" in errors[0]
    assert "No change is needed" in errors[0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
