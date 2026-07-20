"""Operation-ledger adapters — one per registered kind."""

from .assignment import AssignmentAdapter
from .page import PageAdapter
from .quick_assignment import QuickAssignmentAdapter
from .quiz import QuizAdapter
from .rubric import RubricAdapter
from .sweep import SweepAdapter

__all__ = [
    "AssignmentAdapter", "PageAdapter",
    "QuickAssignmentAdapter", "QuizAdapter", "RubricAdapter", "SweepAdapter",
]
