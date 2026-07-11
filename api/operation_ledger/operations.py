"""Operation CRUD helpers — thin wrappers over storage.upsert_operation / find_operation."""
import copy

from . import models, storage


def create_operation(operation: dict) -> dict:
    """Persist a new operation record. Returns a deep copy."""
    return storage.upsert_operation(operation)


def get_operation(operation_id: str) -> dict | None:
    return storage.find_operation(operation_id)


def list_operations() -> list[dict]:
    """Return all operations (deep-copied)."""
    doc = storage.read_operations_document()
    return copy.deepcopy(doc["operations"])


def list_operations_pii_minimized() -> list[dict]:
    """PII-minimized projection for GET /api/operations.

    No course IDs, no payload, no target details.
    """
    ops = list_operations()
    out = []
    for op in ops:
        out.append({
            "operation_id": op.get("operation_id"),
            "kind": op.get("kind"),
            "status": op.get("status"),
            "target_count": len(op.get("targets") or []),
            "created_at": op.get("created_at"),
            "updated_at": op.get("updated_at"),
        })
    return out


def update_operation(operation_id: str, mutator) -> dict:
    """Atomically read-modify-write an operation.

    ``mutator`` receives a deep copy and must return the (possibly modified)
    operation dict. The result is persisted and returned.
    """
    op = storage.find_operation(operation_id)
    if op is None:
        raise KeyError(f"operation {operation_id} not found")
    op = mutator(op)
    op["updated_at"] = models.now_iso()
    return storage.upsert_operation(op)


def set_operation_status(operation_id: str, status: str) -> dict:
    def _set(op):
        op["status"] = status
        return op
    return update_operation(operation_id, _set)


def set_operation_review(operation_id: str, batch: dict) -> dict:
    def _set(op):
        op["review"] = batch
        old = op.get("status", "prepared")
        if models.validate_operation_status_transition(old, "reviewed"):
            op["status"] = "reviewed"
        return op
    return update_operation(operation_id, _set)


def update_target(operation_id: str, target_key: str, mutator) -> dict:
    """Atomically read-modify-write a single target within an operation."""
    def _target_mutator(op):
        for t in op.get("targets", []):
            if t.get("target_key") == target_key:
                t = mutator(t)
                # mutator returns the updated target; find and replace
                break
        return op

    # We need a version that actually replaces the target in the list:
    def _real_mutator(op):
        for i, t in enumerate(op.get("targets", [])):
            if t.get("target_key") == target_key:
                updated = mutator(copy.deepcopy(t))
                op["targets"][i] = updated
                break
        return op
    return update_operation(operation_id, _real_mutator)
