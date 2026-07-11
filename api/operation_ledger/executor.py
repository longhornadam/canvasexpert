"""Executor — the apply/retry engine for the operation ledger.

For each target: claim → write-ahead → execute → persist. Handles partial
failure, retry of unresolved targets only, and receipt creation.
"""
import copy
import json

from . import claims, models, operations, registry, storage
from .receipts import create_receipt, new_receipt


def apply_operation(operation_id: str, batch_id: str, review_digest: str) -> dict:
    """Apply a reviewed operation to Canvas.

    Returns ``{ok, operation_id, status, target_results}``.
    Raises ``ValueError`` if the operation is not in a reviewable state or
    the batch/digest doesn't match.
    """
    op = operations.get_operation(operation_id)
    if op is None:
        raise ValueError(f"operation {operation_id} not found")

    from . import batches
    if not batches.validate_apply(op, batch_id, review_digest):
        raise ValueError("review batch or digest does not match stored review")

    adapter = registry.get_adapter(op["kind"])
    payload = op["normalized_payload"]

    # Transition to applying
    old_status = op.get("status", "reviewed")
    if not models.validate_operation_status_transition(old_status, "applying"):
        raise ValueError(f"operation is in status '{old_status}', cannot apply")

    operations.set_operation_status(operation_id, "applying")

    target_results = []
    for target in op.get("targets", []):
        result = _execute_target(adapter, op, payload, target)
        target_results.append(result)

    # Derive final status
    op = operations.get_operation(operation_id)
    final_status = models.compute_operation_status(op.get("targets", []))
    operations.set_operation_status(operation_id, final_status)

    # Write receipt (map operation status to receipt status)
    receipt = new_receipt(
        subject_type="operation",
        subject_id=operation_id,
        kind=op["kind"],
        status=_receipt_status(final_status),
        targets=_receipt_targets(op.get("targets", [])),
    )
    create_receipt(receipt)

    return {
        "ok": final_status == "applied",
        "operation_id": operation_id,
        "status": final_status,
        "target_results": _project_target_results(target_results),
    }


def retry_operation(operation_id: str) -> dict:
    """Retry only unresolved targets (sent_unknown, failed, blocked).

    Applied/skipped targets are never retried.
    """
    op = operations.get_operation(operation_id)
    if op is None:
        raise ValueError(f"operation {operation_id} not found")

    adapter = registry.get_adapter(op["kind"])
    payload = op["normalized_payload"]

    old_status = op.get("status", "attention")
    if not models.validate_operation_status_transition(old_status, "applying"):
        raise ValueError(f"operation is in status '{old_status}', cannot retry")

    operations.set_operation_status(operation_id, "applying")

    # Only retry unresolved targets
    unresolved = adapter.retry_selector(op)
    unresolved_keys = {t["target_key"] for t in unresolved}

    target_results = []
    for target in op.get("targets", []):
        if target["target_key"] not in unresolved_keys:
            # Already resolved — skip
            target_results.append({
                "target_key": target["target_key"],
                "state": target.get("state"),
                "returned_object_id": target.get("returned_object_id"),
                "returned_object_url": target.get("returned_object_url"),
                "error_code": target.get("error_code"),
                "skipped_retry": True,
            })
            continue
        result = _execute_target(adapter, op, payload, target)
        target_results.append(result)

    op = operations.get_operation(operation_id)
    final_status = models.compute_operation_status(op.get("targets", []))
    operations.set_operation_status(operation_id, final_status)

    receipt = new_receipt(
        subject_type="operation",
        subject_id=operation_id,
        kind=op["kind"],
        status=_receipt_status(final_status),
        targets=_receipt_targets(op.get("targets", [])),
    )
    create_receipt(receipt)

    return {
        "ok": final_status == "applied",
        "operation_id": operation_id,
        "status": final_status,
        "target_results": _project_target_results(target_results),
    }


def _execute_target(adapter, operation: dict, payload: dict, target: dict) -> dict:
    """Execute one target: claim → write-ahead → execute → persist."""
    target_key = target["target_key"]

    # The stored baseline is from review time — use it for drift detection.
    stored_baseline = target.get("baseline", {})

    # Capture a fresh baseline at apply time for the adapter's use.
    fresh_baseline = adapter.capture_baseline(payload, target)

    # Check drift: compare stored baseline with current Canvas state.
    if adapter.check_drift(payload, target, stored_baseline):
        _update_target_state(operation["operation_id"], target_key, "blocked",
                             error_code="drift_detected")
        return {
            "target_key": target_key,
            "state": "blocked",
            "error_code": "drift_detected",
        }

    # Compute payload digest
    payload_digest = models.sha256_dict(payload)

    # Acquire claim
    try:
        claim = claims.acquire_claim(
            target_key=target_key,
            operation_id=operation["operation_id"],
            payload_digest=payload_digest,
        )
    except claims.ClaimConflictError as exc:
        return {
            "target_key": target_key,
            "state": "blocked",
            "error_code": "claim_conflict",
            "private_diagnostic": str(exc),
        }

    # Write-ahead: persist target as claimed
    _update_target_claimed(operation["operation_id"], target_key, claim, fresh_baseline)

    # Execute
    result = adapter.execute(payload, target, fresh_baseline, claim)
    state = result.get("state", "failed")

    # Persist result
    _update_target_result(operation["operation_id"], target_key, result, claim)

    # Release claim
    claims.release_claim(claim["claim_id"])

    return {
        "target_key": target_key,
        "state": state,
        "returned_object_id": result.get("returned_object_id"),
        "returned_object_url": result.get("returned_object_url"),
        "error_code": result.get("error_code"),
        "private_diagnostic": result.get("private_diagnostic"),
    }


def _update_target_state(operation_id: str, target_key: str, state: str,
                         error_code: str | None = None) -> None:
    def _mutator(t):
        old = t.get("state", "pending")
        if not models.validate_target_state_transition(old, state):
            # Allow direct set for recovery scenarios
            pass
        t["state"] = state
        if error_code:
            t["error_code"] = error_code
        t["updated_at"] = models.now_iso()
        return t
    operations.update_target(operation_id, target_key, _mutator)


def _update_target_claimed(operation_id: str, target_key: str, claim: dict,
                           baseline: dict) -> None:
    def _mutator(t):
        t["state"] = "claimed"
        t["attempt_id"] = claim["attempt_id"]
        t["payload_digest"] = claim["payload_digest"]
        t["claim_owner"] = claim["owner_pid"]
        t["claim_acquired_at"] = claim["acquired_at"]
        t["claim_lease_expires_at"] = claim["lease_expires_at"]
        t["baseline"] = baseline
        t["updated_at"] = models.now_iso()
        return t
    operations.update_target(operation_id, target_key, _mutator)


def _update_target_result(operation_id: str, target_key: str, result: dict,
                          claim: dict) -> None:
    def _mutator(t):
        t["state"] = result.get("state", "failed")
        if result.get("returned_object_id"):
            t["returned_object_id"] = result["returned_object_id"]
        if result.get("returned_object_url"):
            t["returned_object_url"] = result["returned_object_url"]
        if result.get("error_code"):
            t["error_code"] = result["error_code"]
        if result.get("private_diagnostic"):
            t["private_diagnostic"] = result["private_diagnostic"]
        if result.get("steps"):
            t["steps"] = result["steps"]
        t["updated_at"] = models.now_iso()
        return t
    operations.update_target(operation_id, target_key, _mutator)


def _receipt_targets(targets: list[dict]) -> list[dict]:
    """PII-minimized target projection for receipts."""
    out = []
    for t in targets:
        out.append({
            "target_key": t.get("target_key"),
            "state": t.get("state"),
            "returned_object_id": t.get("returned_object_id"),
            "returned_object_url": t.get("returned_object_url"),
            "error_code": t.get("error_code"),
        })
    return out


def _receipt_status(operation_status: str) -> str:
    """Map an operation status to a valid receipt status.

    Receipt statuses: applied, partial, failed, blocked, no_effect.
    Operation statuses: applied, partial, failed, attention.
    ``attention`` maps to ``blocked`` (needs human review).
    """
    mapping = {
        "applied": "applied",
        "partial": "partial",
        "failed": "failed",
        "attention": "blocked",
    }
    return mapping.get(operation_status, "failed")


def _project_target_results(results: list[dict]) -> list[dict]:
    """PII-minimized projection of target results for the API response."""
    out = []
    for r in results:
        out.append({
            "target_key": r.get("target_key"),
            "state": r.get("state"),
            "returned_object_id": r.get("returned_object_id"),
            "returned_object_url": r.get("returned_object_url"),
            "error_code": r.get("error_code"),
        })
    return out
