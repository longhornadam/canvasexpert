"""Machine-local operation-ledger primitives."""

from .receipts import create_receipt, list_receipts, get_receipt, new_receipt
from . import models, operations, batches, registry, executor, claims, recovery
from .adapters import (
    AssignmentAdapter, ExtensionAdapter, PageAdapter, QuickAssignmentAdapter,
    QuizAdapter, RubricAdapter, SweepAdapter,
)

__all__ = [
    "create_receipt", "list_receipts", "get_receipt", "new_receipt",
    "models", "operations", "batches", "registry", "executor", "claims",
    "recovery",
    "AssignmentAdapter", "ExtensionAdapter", "PageAdapter",
    "QuickAssignmentAdapter", "QuizAdapter", "RubricAdapter", "SweepAdapter",
]

registry.register(AssignmentAdapter())
registry.register(ExtensionAdapter())
registry.register(PageAdapter())
registry.register(QuickAssignmentAdapter())
registry.register(QuizAdapter())
registry.register(RubricAdapter())
registry.register(SweepAdapter())
