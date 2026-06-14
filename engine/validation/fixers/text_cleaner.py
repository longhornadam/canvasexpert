"""Text cleaning fixer.

Normalizes whitespace, fixes smart quotes, etc.
"""

from typing import List, Tuple
from ...core.quiz import Quiz
from ...utils.text_utils import sanitize_text


class TextCleaner:
    """Clean and normalize text in quiz."""
    
    def clean(self, quiz: Quiz) -> Tuple[Quiz, List[str]]:
        """Clean text in all questions.
        
        Args:
            quiz: Quiz to clean
            
        Returns:
            Tuple of (quiz, log_messages)
        """
        messages: List[str] = []
        
        # Clean quiz title
        quiz.title = sanitize_text(quiz.title)
        
        # Clean all question prompts
        for question in quiz.questions:
            question.prompt = sanitize_text(question.prompt)
        
        messages.append("Cleaned text (normalized quotes, whitespace)")
        return quiz, messages