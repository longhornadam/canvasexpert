"""Numerical bounds calculator.

Calculates lower/upper bounds for numerical questions.
"""

from typing import List, Tuple
from decimal import Decimal
from ...core.quiz import Quiz
from ...core.questions import NumericalQuestion


class BoundsCalculator:
    """Calculate bounds for numerical questions."""
    
    def calculate(self, quiz: Quiz) -> Tuple[Quiz, List[str]]:
        """Calculate bounds for all numerical questions.
        
        Args:
            quiz: Quiz to process
            
        Returns:
            Tuple of (quiz, log_messages)
        """
        messages: List[str] = []
        
        for question in quiz.questions:
            if isinstance(question, NumericalQuestion):
                # Bounds should already be calculated by parser
                # This is a safety check
                if question.answer.lower_bound is None or question.answer.upper_bound is None:
                    messages.append(f"Warning: Numerical question missing bounds: {question.prompt[:30]}...")
        
        return quiz, messages