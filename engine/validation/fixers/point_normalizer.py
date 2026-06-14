"""Point normalization fixer.

Distributes points across scorable questions to total 100.
"""

from typing import List, Tuple
from ...core.quiz import Quiz


class PointNormalizer:
    """Normalize quiz points to total 100."""
    
    def normalize(self, quiz: Quiz, target_total: float = 100.0) -> Tuple[Quiz, List[str]]:
        """Normalize points across scorable questions.
        
        Only normalizes questions where points_set is False.
        
        Args:
            quiz: Quiz to normalize
            target_total: Target point total (default 100)
            
        Returns:
            Tuple of (quiz, log_messages)
        """
        messages: List[str] = []
        scorable = quiz.scorable_questions()
        
        # Check if any questions need normalization
        needs_normalization = any(not q.points_set for q in scorable)
        if not needs_normalization:
            return quiz, messages
        
        # Get questions to normalize (those without explicit points)
        to_normalize = [q for q in scorable if not q.points_set]
        
        if not to_normalize:
            return quiz, messages
        
        # Calculate current total of explicit points
        explicit_total = sum(q.points for q in scorable if q.points_set)
        remaining = target_total - explicit_total
        
        if remaining <= 0:
            messages.append(
                f"Warning: Explicit points total {explicit_total}, leaving {remaining} "
                f"for auto-distribution. Using equal distribution anyway."
            )
            remaining = target_total
        
        # Distribute remaining points equally
        points_each = remaining / len(to_normalize)
        
        for q in to_normalize:
            q.points = round(points_each)
        
        # Adjust for rounding errors
        actual_total = sum(q.points for q in scorable)
        diff = int(target_total - actual_total)
        
        if diff != 0:
            # Add/subtract from first question to hit target exactly
            to_normalize[0].points += diff
        
        messages.append(
            f"Normalized {len(to_normalize)} questions to total {target_total} points"
        )
        
        return quiz, messages