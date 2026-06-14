"""Choice randomization fixer.

Shuffles MC/MA answer choices and breaks detectable patterns.
"""

import random
from typing import List, Tuple
from ...core.quiz import Quiz
from ...core.questions import MCQuestion, MAQuestion


class ChoiceRandomizer:
    """Randomize answer choices and break patterns."""
    
    def randomize(self, quiz: Quiz) -> Tuple[Quiz, List[str]]:
        """Shuffle answer choices for MC/MA questions.
        
        Args:
            quiz: Quiz to randomize
            
        Returns:
            Tuple of (quiz, log_messages)
        """
        messages: List[str] = []
        
        # TODO: Implement sophisticated shuffling with pattern breaking
        # For now, just shuffle each question
        for question in quiz.questions:
            if isinstance(question, (MCQuestion, MAQuestion)):
                if question.choices:
                    random.shuffle(question.choices)
                    messages.append(f"Shuffled choices for question: {question.prompt[:30]}...")
        
        return quiz, messages