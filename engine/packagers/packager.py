"""Main packaging router.

Unified entry point that routes to Canvas and Physical output generators.
"""

from typing import Dict
from engine.core.quiz import Quiz
from .canvas_handler import CanvasHandler
from .physical_handler import PhysicalHandler


def package_quiz(quiz: Quiz, output_base: str) -> Dict[str, Dict[str, str]]:
    """
    Main entry point. Always generates both Canvas and Physical outputs.
    
    Args:
        quiz: Validated Quiz object
        output_base: Base directory for output files
        
    Returns:
        {
            'canvas': {'qti_path': str, 'log_path': str},
            'physical': {'quiz_path': str, 'key_path': str, 'rationale_path': str, 'log_path': str}
        }
    """
    # Shared validation - assume quiz is validated
    
    # Route to canvas_handler
    canvas_handler = CanvasHandler()
    canvas_result = canvas_handler.package(quiz, output_base)
    
    # Route to physical_handler
    physical_handler = PhysicalHandler()
    physical_result = physical_handler.package(quiz, output_base)
    
    # Return combined results
    return {
        'canvas': canvas_result,
        'physical': physical_result
    }