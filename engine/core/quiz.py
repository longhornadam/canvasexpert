"""Quiz domain model.

A Quiz is the top-level aggregate containing all questions and metadata.
This is the primary data structure that flows through the system:
    TXT file → Parser → Quiz → Validator → Quiz (validated) → Renderers → Output
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from .questions import Question, StimulusItem


@dataclass
class Quiz:
    """Quiz aggregate: title + list of questions."""
    
    title: str
    questions: List['Question'] = field(default_factory=list)
    rationales: List = field(default_factory=list)
    instructions: str = ""
    
    def total_points(self) -> float:
        """Calculate total points across all scorable questions.
        
        Returns:
            Total point value (excludes StimulusItem which have 0 points)
        """
        return sum(q.points for q in self.questions)
    
    def scorable_questions(self) -> List['Question']:
        """Return only questions that contribute to the score.
        
        Excludes StimulusItem objects (0-point content blocks).
        
        Returns:
            List of questions with point values
        """
        from .questions import StimulusItem, StimulusEnd
        return [q for q in self.questions if not isinstance(q, (StimulusItem, StimulusEnd))]
    
    def question_count(self) -> int:
        """Get total number of questions (including stimuli).
        
        Returns:
            Total question count
        """
        return len(self.questions)
    
    def scorable_count(self) -> int:
        """Get count of scorable questions only.
        
        Returns:
            Number of questions that contribute to score
        """
        return len(self.scorable_questions())

    def has_rationales(self) -> bool:
        """Check if rationales exist for all scorable questions."""
        scorable = self.scorable_questions()
        # Subtract ESSAY/FILEUPLOAD which don't need rationales
        expected = len([q for q in scorable if q.qtype not in ['ESSAY', 'FILEUPLOAD']])
        return len(self.rationales) >= expected
