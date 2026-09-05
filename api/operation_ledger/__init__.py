"""Machine-local operation-ledger primitives."""

from .receipts import create_receipt, list_receipts, get_receipt, new_receipt
from . import models, operations, batches, registry, executor, claims, recovery
from .adapters import (
    AssignmentAdapter, PageAdapter, QuickAssignmentAdapter,
    QuizAdapter, RubricAdapter, SeatingGroupSetAdapter, SisGradeBridgeAdapter,
    SweepAdapter,
)

__all__ = [
    "create_receipt", "list_receipts", "get_receipt", "new_receipt",
    "models", "operations", "batches", "registry", "executor", "claims",
    "recovery",
    "AssignmentAdapter", "PageAdapter",
    "QuickAssignmentAdapter", "QuizAdapter", "RubricAdapter", "SeatingGroupSetAdapter",
    "SisGradeBridgeAdapter", "SweepAdapter",
]

registry.register(AssignmentAdapter())
registry.register(PageAdapter())
registry.register(QuickAssignmentAdapter())
registry.register(QuizAdapter())
registry.register(RubricAdapter())
registry.register(SeatingGroupSetAdapter())
registry.register(SisGradeBridgeAdapter())
registry.register(SweepAdapter())
