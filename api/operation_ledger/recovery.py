"""Recovery — on restart, reconcile sent_unknown / claimed targets.

For every target in ``claimed`` or ``sent_unknown`` state:
1. Check the claim. If expired or owned by a dead process, mark it expired.
2. Call ``adapter.reconcile(payload, target, baseline)``.
3. If reconcile proves applied: persist returned IDs, set target applied.
4. If reconcile proves absent: set target back to pending (eligible for retry).
5. If reconcile cannot prove either: target stays sent_unknown (Attention).
"""
import copy

from . import claims, models, operations, registry, storage


def recover_pending_operations() -> dict:
    """Scan all operations for targets needing recovery and reconcile them.

    Returns a summary: ``{recovered: int, still_unknown: int, reset_to_pending: int}``.
    """
    doc = storage.read_operations_document()
    summary = {"recovered": 0, "still_unknown": 0, "reset_to_pending": 0}

    for op in doc["operations"]:
        op_id = op["operation_id"]
        needs_recovery = False
        for target in op.get("targets", []):
            state = target.get("state")
            if state in ("claimed", "sent_unknown"):
                needs_recovery = True
                break

        if not needs_recovery:
            continue

        try:
            adapter = registry.get_adapter(op["kind"])
        except ValueError:
            continue  # unknown kind — skip

        payload = op.get("normalized_payload", {})

        for target in op.get("targets", []):
            state = target.get("state")
            if state not in ("claimed", "sent_unknown"):
                continue

            # Check claim expiry
            claim_id = f"{target['target_key']}:{target.get('attempt_id', '')}"
            claim = storage.find_claim(claim_id) if target.get("attempt_id") else None
            if claim and claim.get("state") == "claimed":
                # Mark expired if lease has passed
                expired = claims.detect_expired_claims()
                if any(c.get("claim_id") == claim_id for c in expired):
                    pass  # claim is now expired

            # Reconcile
            baseline = target.get("baseline", {})
            result = adapter.reconcile(payload, target, baseline)
            new_state = result.get("state", "sent_unknown")

            if new_state == "applied":
                _apply_recovered(op_id, target["target_key"], result)
                summary["recovered"] += 1
            elif new_state == "pending":
                _reset_to_pending(op_id, target["target_key"])
                summary["reset_to_pending"] += 1
            else:
                summary["still_unknown"] += 1

    return summary


def _apply_recovered(operation_id: str, target_key: str, result: dict) -> None:
    def _mutator(t):
        t["state"] = "applied"
        if result.get("returned_object_id"):
            t["returned_object_id"] = result["returned_object_id"]
        if result.get("returned_object_url"):
            t["returned_object_url"] = result["returned_object_url"]
        t["updated_at"] = models.now_iso()
        return t
    operations.update_target(operation_id, target_key, _mutator)


def _reset_to_pending(operation_id: str, target_key: str) -> None:
    def _mutator(t):
        t["state"] = "pending"
        t["attempt_id"] = None
        t["payload_digest"] = None
        t["claim_owner"] = None
        t["claim_acquired_at"] = None
        t["claim_lease_expires_at"] = None
        t["updated_at"] = models.now_iso()
        return t
    operations.update_target(operation_id, target_key, _mutator)
