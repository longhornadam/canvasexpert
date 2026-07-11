"""Operation-ledger adapters — one per registered kind."""

from .assignment import AssignmentAdapter
from .page import PageAdapter
from .quick_assignment import QuickAssignmentAdapter
from .rubric import RubricAdapter

__all__ = ["AssignmentAdapter", "PageAdapter", "QuickAssignmentAdapter",
           "RubricAdapter"]
