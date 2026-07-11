"""Operation-ledger adapters — one per registered kind."""

from .assignment import AssignmentAdapter
from .page import PageAdapter
from .quick_assignment import QuickAssignmentAdapter

__all__ = ["AssignmentAdapter", "PageAdapter", "QuickAssignmentAdapter"]
