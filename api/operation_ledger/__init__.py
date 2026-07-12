"""Machine-local operation-ledger primitives."""

from .receipts import create_receipt, list_receipts, get_receipt, new_receipt
from . import models, operations, batches, registry, executor, claims, recovery
from .adapters import (
    AssignmentAdapter, CurveAdapter, ExtensionAdapter, LatePolicyAdapter,
    PageAdapter, QuickAssignmentAdapter, RubricAdapter, SweepAdapter,
)

__all__ = [
    "create_receipt", "list_receipts", "get_receipt", "new_receipt",
    "models", "operations", "batches", "registry", "executor", "claims",
    "recovery",
    "AssignmentAdapter", "CurveAdapter", "ExtensionAdapter", "LatePolicyAdapter",
    "PageAdapter", "QuickAssignmentAdapter", "RubricAdapter", "SweepAdapter",
]

registry.register(AssignmentAdapter())
registry.register(CurveAdapter())
registry.register(ExtensionAdapter())
registry.register(LatePolicyAdapter())
registry.register(PageAdapter())
registry.register(QuickAssignmentAdapter())
registry.register(RubricAdapter())
registry.register(SweepAdapter())
