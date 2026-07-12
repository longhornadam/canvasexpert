"""Machine-local operation-ledger primitives."""

from .receipts import create_receipt, list_receipts, get_receipt, new_receipt
from . import models, operations, batches, registry, executor, claims, recovery
from .adapters import (
    AssignmentAdapter, CurveAdapter, ExtensionAdapter, GroupSetAdapter,
    LatePolicyAdapter, MembershipAdapter, PageAdapter, QuickAssignmentAdapter,
    QuizAdapter, RubricAdapter, SweepAdapter,
)

__all__ = [
    "create_receipt", "list_receipts", "get_receipt", "new_receipt",
    "models", "operations", "batches", "registry", "executor", "claims",
    "recovery",
    "AssignmentAdapter", "CurveAdapter", "ExtensionAdapter", "GroupSetAdapter",
    "LatePolicyAdapter", "MembershipAdapter", "PageAdapter",
    "QuickAssignmentAdapter", "QuizAdapter", "RubricAdapter", "SweepAdapter",
]

registry.register(AssignmentAdapter())
registry.register(CurveAdapter())
registry.register(ExtensionAdapter())
registry.register(GroupSetAdapter())
registry.register(LatePolicyAdapter())
registry.register(MembershipAdapter())
registry.register(PageAdapter())
registry.register(QuickAssignmentAdapter())
registry.register(QuizAdapter())
registry.register(RubricAdapter())
registry.register(SweepAdapter())
