"""Fairness validation rules.

These rules check for patterns that may indicate bias:
- Longest answer is always correct
- Shortest answer is always correct

Answer-position balancing is handled by the auto-fixer (answer_balancer) to avoid
user-facing noise about shuffling the user cannot control.
"""

from typing import List, Optional
from ...core.quiz import Quiz
from ...core.questions import MCQuestion, MAQuestion


# Standardized meta-answers (must match exactly - see LLM_Modules/QuizForge_Base.md Section 10)
# These serve structural/logical purposes rather than content-based choices
META_ANSWERS = {
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

# Suggestions for common non-standard variations
# Guides authors toward standardized phrasings when validation fails
META_ANSWER_SUGGESTIONS = {
    "no changes are needed": "No change is needed",
    "no change needed": "No change is needed",
    "no correction required": "No change is needed",
    "no correction is needed": "No change is needed",
    "no changes needed": "No change is needed",
    "no changes are needed in this sentence": "No change is needed",
    "no change needed for this one": "No change is needed",
    "no correction required here": "No change is needed",
    "all three sentences": "All of the above",
    "all are correct": "All of the above",
    "all of these": "All of the above",
    "all choices": "All of the above",
    "all three choices": "All of the above",
    "all sentences equally support": "All of the above",
    "none are correct": "None of the above",
    "none of the choices": "None of the above",
    "neither a nor b": "Neither is correct",
    "both are correct": "Both A and B",
    "both a and c are correct": "Both A and C",
    "both a and d are correct": "Both A and D",
    "both b and c are correct": "Both B and C",
    "both b and d are correct": "Both B and D",
    "both c and d are correct": "Both C and D",
}


def _suggest_meta_answer(choice_text: str) -> Optional[str]:
    """If text looks like a meta-answer variation, suggest the standardized form.
    
    This helps authors migrate to standardized phrasings by providing helpful
    suggestions when validation fails.
    
    Args:
        choice_text: The answer choice text to check
        
    Returns:
        Suggested standard meta-answer, or None if no match found
    """
    if not choice_text:
        return None
    normalized = choice_text.strip().lower()
    return META_ANSWER_SUGGESTIONS.get(normalized)


def _is_meta_answer(text: str) -> bool:
    """Identifies standardized meta-answers that shouldn't factor into length bias detection.
    
    Meta-answers serve structural/logical purposes rather than content-based choices.
    Students evaluate them differently, so comparing their length to substantive
    answers creates false positives.
    
    These exact phrasings are required by LLM_Modules/QuizForge_Base.md Section 10.
    LLMs are instructed to use only these standardized forms.
    
    Args:
        text: The choice text to check
        
    Returns:
        True if the choice is a standardized meta-answer, False otherwise
    """
    if not text:
        return False
    return text.strip() in META_ANSWERS


def check_fairness(quiz: Quiz) -> List[str]:
    """Return fairness warnings (currently none; length bias is treated as an error elsewhere)."""
    return []


def check_length_bias(quiz: Quiz) -> List[str]:
    """Check for length bias in MC questions; returns error messages if biased.
    
    Excludes meta-answers (like "No change is needed", "All of the above") from
    length calculations, as they serve structural purposes and shouldn't be compared
    with content-based choices.
    """
    errors: List[str] = []
    mc_questions = [q for q in quiz.questions if isinstance(q, MCQuestion)]
    # Skip tiny sets; length bias is meaningless on very small samples
    if len(mc_questions) < 3:
        return errors

    longest_correct_count = 0
    shortest_correct_count = 0
    questions_with_substantive_choices = 0
    
    for question in mc_questions:
        if not question.choices:
            continue
        
        # Filter out meta-answers from length comparison
        substantive_choices = [c for c in question.choices if not _is_meta_answer(c.text)]
        
        # Only validate if we have 2+ substantive choices to compare
        if len(substantive_choices) < 2:
            continue
        
        questions_with_substantive_choices += 1
        longest = max(substantive_choices, key=lambda c: len(c.text))
        shortest = min(substantive_choices, key=lambda c: len(c.text))
        
        if longest.correct:
            longest_correct_count += 1
        if shortest.correct:
            shortest_correct_count += 1

    total = questions_with_substantive_choices
    if total == 0:
        return errors

    longest_pct = (longest_correct_count / total) * 100
    shortest_pct = (shortest_correct_count / total) * 100

    if longest_pct >= 60:
        error_msg = (
            f"Longest answer is correct in {longest_pct:.0f}% of MC questions "
            f"({longest_correct_count}/{total}). Balance answer lengths by shortening correct answers or lengthening distractors so the right answer is not obviously the longest."
        )
        
        # Check if any correct answers are non-standard meta-answer variations
        suggestions_found = []
        for question in mc_questions:
            if not question.choices:
                continue
            correct = next((c for c in question.choices if c.correct), None)
            if correct:
                suggestion = _suggest_meta_answer(correct.text)
                if suggestion and suggestion not in suggestions_found:
                    suggestions_found.append(suggestion)
        
        if suggestions_found:
            error_msg += "\n  💡 Tip: Consider using standardized meta-answer(s): " + ", ".join(f"'{s}'" for s in suggestions_found)
        
        errors.append(error_msg)
        
    if shortest_pct >= 60:
        error_msg = (
            f"Shortest answer is correct in {shortest_pct:.0f}% of MC questions "
            f"({shortest_correct_count}/{total}). Balance answer lengths by padding distractors or tightening the correct answer so it is not obviously the shortest."
        )
        
        # Check if any correct answers are non-standard meta-answer variations
        suggestions_found = []
        for question in mc_questions:
            if not question.choices:
                continue
            correct = next((c for c in question.choices if c.correct), None)
            if correct:
                suggestion = _suggest_meta_answer(correct.text)
                if suggestion and suggestion not in suggestions_found:
                    suggestions_found.append(suggestion)
        
        if suggestions_found:
            error_msg += "\n  💡 Tip: Consider using standardized meta-answer(s): " + ", ".join(f"'{s}'" for s in suggestions_found)
        
        errors.append(error_msg)

    return errors


def _check_answer_position_pattern(questions: List[MCQuestion]) -> List[str]:
    """Deprecated: answer-position streak warnings are suppressed (see check_fairness)."""
    return []

