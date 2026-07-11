"""Recovery — on restart, reconcile sent_unknown / claimed targets.

For every target in ``claimed`` or ``sent_unknown`` state:
1. Skip an unexpired active claim. If expired, mark it expired.
2. Call ``adapter.reconcile(payload, target, baseline)``.
3. If reconcile proves applied: persist returned IDs, set target applied.
4. If reconcile proves absent: set target back to pending (eligible for retry).
5. If reconcile cannot prove either: target stays sent_unknown (Attention).
"""
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

            # An active lease blocks recovery regardless of PID.
            claim_id = f"{target['target_key']}:{target.get('attempt_id', '')}"
            claim = storage.find_claim(claim_id) if target.get("attempt_id") else None
            if claim and claim.get("state") == "claimed":
                if not claims._is_claim_expired(claim):
                    continue
                claims.detect_expired_claims()
                claim = storage.find_claim(claim_id)
                if claim and claim.get("state") == "claimed":
                    continue

            # Reconcile
            baseline = target.get("baseline", {})
            result = adapter.reconcile(payload, target, baseline)
            if claim and claim.get("state") == "expired":
                claims.mark_reconciled(claim_id)
            new_state = result.get("state", "sent_unknown")

            if new_state == "applied":
                _apply_recovered(op_id, target["target_key"], result)
                summary["recovered"] += 1
            elif new_state == "pending":
                if _has_outbound_marker(target):
                    summary["still_unknown"] += 1
                else:
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
        if result.get("module_item_id"):
            for step in t.get("steps", []):
                if step.get("step_key") == "attach_module":
                    step["returned_object_id"] = result["module_item_id"]
                    step["state"] = "applied"
                    break
        t["claim_owner"] = None
        t["claim_acquired_at"] = None
        t["claim_lease_expires_at"] = None
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


def _has_outbound_marker(target: dict) -> bool:
    return any(step.get("outbound_started_at") for step in target.get("steps", []))
