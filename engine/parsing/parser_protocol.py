"""Parser protocol definition.

Defines the interface that all quiz parsers must implement.
This allows swapping parsers without changing downstream code.
"""

from typing import Protocol, Optional
from ..core.quiz import Quiz


class QuizParser(Protocol):
    """Protocol for converting authoring artifacts into Quiz aggregates.
    
    Any class implementing this protocol can be used by the orchestrator.
    """
    
    def parse_file(self, filepath: str, title_override: Optional[str] = None) -> Quiz:
        """Parse quiz from file path.
        
        Args:
            filepath: Path to quiz file
            title_override: Optional title to override quiz title
            
        Returns:
            Quiz object
        """
        ...
    
    def parse_text(self, content: str, title_override: Optional[str] = None) -> Quiz:
        """Parse quiz from text content.
        
        Args:
            content: Raw quiz text
            title_override: Optional title override
            
        Returns:
            Quiz object
        """
        ...