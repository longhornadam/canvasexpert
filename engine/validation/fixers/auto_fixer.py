"""Auto-fix orchestrator.

Coordinates all automatic fixes:
- Point normalization
- Answer balancing (shuffling)
- Text cleaning
- Bounds calculation
"""

from typing import List, Tuple
from ...core.quiz import Quiz
from . import point_normalizer, text_cleaner, bounds_calculator
from .. import answer_balancer


class AutoFixer:
    """Coordinate automatic quiz fixes."""
    
    def __init__(self):
        """Initialize auto-fixer with sub-fixers."""
        self.point_normalizer = point_normalizer.PointNormalizer()
        self.text_cleaner = text_cleaner.TextCleaner()
        self.bounds_calculator = bounds_calculator.BoundsCalculator()
    
    def fix_all(self, quiz: Quiz) -> Tuple[Quiz, List[str]]:
        """Apply all automatic fixes to quiz.
        
        Fixes applied in order:
        1. Clean text (normalize whitespace, fix smart quotes)
        2. Calculate numerical bounds
        3. Normalize points to 100
        4. Randomize answer choices
        
        Args:
            quiz: Quiz object to fix
            
        Returns:
            Tuple of (fixed_quiz, list_of_changes)
        """
        fix_log: List[str] = []
        
        # Fix 1: Clean text
        quiz, clean_msgs = self.text_cleaner.clean(quiz)
        fix_log.extend(clean_msgs)
        
        # Fix 2: Calculate numerical bounds
        quiz, bounds_msgs = self.bounds_calculator.calculate(quiz)
        fix_log.extend(bounds_msgs)
        
        # Fix 3: Normalize points
        quiz, point_msgs = self.point_normalizer.normalize(quiz)
        fix_log.extend(point_msgs)
        
        # Fix 4: Balance and shuffle answers (MC/MA/TF)
        answer_balancer.balance_answers(quiz.questions)
        fix_log.append("Balanced answer distributions (shuffled MC/MA/TF correct positions)")
        
        return quiz, fix_log
