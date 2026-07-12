"""Operation-ledger adapters — one per registered kind."""

from .assignment import AssignmentAdapter
from .extension import ExtensionAdapter
from .late_policy import LatePolicyAdapter
from .page import PageAdapter
from .quick_assignment import QuickAssignmentAdapter
from .rubric import RubricAdapter
from .sweep import SweepAdapter

__all__ = [
    "AssignmentAdapter", "ExtensionAdapter", "LatePolicyAdapter", "PageAdapter",
    "QuickAssignmentAdapter", "RubricAdapter", "SweepAdapter",
]
