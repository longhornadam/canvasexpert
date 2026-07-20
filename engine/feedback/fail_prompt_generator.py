"""Generate LLM revision prompts for FAIL outcomes.

Creates QuizName_FAIL_REVISE_WITH_AI.txt containing:
- Original quiz text
- Clear error explanation
- Instructions for LLM to fix the issue
"""

from typing import List


def generate_fail_prompt(
    original_text: str,
    errors: List[str],
    quiz_title: str
) -> str:
    """Generate LLM revision prompt for failed validation.
    
    Args:
        original_text: Original quiz TXT content
        errors: List of validation errors
        quiz_title: Quiz title for context
        
    Returns:
        Formatted prompt text for LLM
    """
    lines = []
    
    # Error report
    lines.append("=" * 60)
    lines.append("VALIDATION ERRORS DETECTED")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"The quiz '{quiz_title}' has critical errors that must be fixed")
    lines.append("before it can be processed. Please fix the following issues:")
    lines.append("")
    
    for i, error in enumerate(errors, 1):
        lines.append(f"{i}. {error}")
    lines.append("")
    
    # Instructions for LLM
    lines.append("=" * 60)
    lines.append("INSTRUCTIONS FOR REVISION")
    lines.append("=" * 60)
    lines.append("")
    lines.append("Please revise the quiz above to fix all the errors listed.")
    lines.append("Make sure:")
    lines.append("  - All required fields are present (Type, Prompt, Choices, etc.)")
    lines.append("  - MC questions have 2-7 choices with exactly 1 correct answer")
    lines.append("  - MA questions have at least 1 correct answer")
    lines.append("  - Numerical questions have valid answer/tolerance/range settings")
    lines.append("  - All questions have non-empty prompts")
    lines.append("")
    lines.append("Once fixed, save the revised quiz as a new .txt file and")
    lines.append("drop it back into the DropZone folder.")
    lines.append("")

    # Original quiz (placed last so errors stay visible at the top)
    lines.append("=" * 60)
    lines.append("ORIGINAL QUIZ (Contains Errors)")
    lines.append("=" * 60)
    lines.append("")
    lines.append(original_text)
    lines.append("")
    
    return "\n".join(lines)
