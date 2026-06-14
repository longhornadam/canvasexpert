"""Generate success logs for PASS/WEAK_PASS outcomes.

Creates log_PASS_WEAK_FIXED.txt with details of:
- Auto-fixes applied
- Warnings detected
- Final quiz statistics
"""

from typing import List
from datetime import datetime


def generate_log(
    fix_log: List[str],
    warnings: List[str],
    quiz_title: str,
    total_points: float,
    question_count: int
) -> str:
    """Generate user-facing success log.
    
    Args:
        fix_log: List of auto-fixes applied
        warnings: List of warnings (for WEAK_PASS)
        quiz_title: Quiz title
        total_points: Total point value
        question_count: Number of questions
        
    Returns:
        Formatted log text
    """
    lines = []
    
    # Header
    lines.append("=" * 60)
    lines.append("QuizForge Processing Log")
    lines.append("=" * 60)
    lines.append(f"Quiz: {quiz_title}")
    lines.append(f"Processed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Questions: {question_count}")
    lines.append(f"Total Points: {total_points}")
    lines.append("")
    
    # Status
    if warnings:
        lines.append("STATUS: WEAK PASS (Warnings detected)")
    else:
        lines.append("STATUS: PASS (No issues)")
    lines.append("")
    
    # Auto-fixes
    if fix_log:
        lines.append("AUTO-FIXES APPLIED:")
        lines.append("-" * 60)
        for i, fix in enumerate(fix_log, 1):
            lines.append(f"{i}. {fix}")
        lines.append("")
    
    # Warnings
    if warnings:
        lines.append("WARNINGS:")
        lines.append("-" * 60)
        for i, warning in enumerate(warnings, 1):
            lines.append(f"{i}. {warning}")
        lines.append("")
        lines.append("Note: These warnings do not prevent quiz generation,")
        lines.append("but you may want to review them for fairness.")
        lines.append("")
    
    # Footer
    lines.append("=" * 60)
    lines.append("Quiz packages generated successfully!")
    lines.append("=" * 60)
    
    return "\n".join(lines)
