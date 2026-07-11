"""Claim / lease management for the operation ledger.

Claims are atomic, machine-local locks on a target. Before any Canvas call,
the executor acquires a claim, flushes it, and only then makes the HTTP request.
On restart, expired claims are detected and their targets reconciled.
"""
import copy
import os
from datetime import datetime, timezone

from . import models, storage


def _process_started_at() -> str:
    """Best-effort process start time for owner identity."""
    try:
        import psutil
        return datetime.fromtimestamp(
            psutil.Process(os.getpid()).create_time(), tz=timezone.utc
        ).isoformat(timespec="seconds")
    except Exception:
        # Fallback: use a module-level constant set at import time.
        return _FALLBACK_STARTED_AT


_FALLBACK_STARTED_AT = datetime.now(timezone.utc).isoformat(timespec="seconds")


def acquire_claim(*, target_key: str, operation_id: str, payload_digest: str) -> dict:
    """Atomically acquire a claim for a target.

    Raises ``ClaimConflictError`` if the target has any unreconciled claimed
    record. Recovery must expire an expired lease before a new attempt starts.
    """
    attempt_id = models.new_attempt_id()
    claim_id = f"{target_key}:{attempt_id}"
    claim = models.new_claim(
        claim_id=claim_id,
        target_key=target_key,
        operation_id=operation_id,
        attempt_id=attempt_id,
        owner_pid=os.getpid(),
        owner_started_at=_process_started_at(),
        payload_digest=payload_digest,
    )

    def _mutator(doc):
        # Check for an existing active claim on this target_key
        for existing in doc["claims"]:
            if existing.get("target_key") != target_key:
                continue
            if existing.get("state") not in ("claimed", "expired"):
                continue
            if existing.get("state") == "expired" and existing.get("reconciled_at"):
                continue
            raise ClaimConflictError(f"target {target_key} is already claimed")
        doc["claims"].append(copy.deepcopy(claim))
        return doc

    storage.modify_claims(_mutator)
    return claim


def release_claim(claim_id: str) -> None:
    """Mark a claim as released (the Canvas call succeeded)."""
    def _mutator(doc):
        for c in doc["claims"]:
            if c.get("claim_id") == claim_id:
                c["state"] = "released"
                break
        return doc
    storage.modify_claims(_mutator)


def mark_reconciled(claim_id: str) -> None:
    """Allow a recovered expired claim to be replaced after reconciliation."""
    def _mutator(doc):
        for item in doc["claims"]:
            if item.get("claim_id") == claim_id and item.get("state") == "expired":
                item["reconciled_at"] = models.now_iso()
                break
        return doc
    storage.modify_claims(_mutator)


def _is_claim_expired(claim: dict) -> bool:
    """A claim is expired only when its elapsed lease is invalid or passed."""
    lease_str = claim.get("lease_expires_at")
    if not lease_str:
        return True
    try:
        lease_dt = datetime.fromisoformat(lease_str)
    except (ValueError, TypeError):
        return True
    if lease_dt.tzinfo is None:
        return True
    return datetime.now(timezone.utc) > lease_dt


def is_current_claim(claim_id: str, target_key: str, operation_id: str) -> bool:
    """Return whether the named claim is still the active claim for a target."""
    claim = storage.find_claim(claim_id)
    return bool(
        claim
        and claim.get("claim_id") == claim_id
        and claim.get("target_key") == target_key
        and claim.get("operation_id") == operation_id
        and claim.get("state") == "claimed"
    )


def detect_expired_claims() -> list[dict]:
    """Return all claims that are currently expired (for restart recovery)."""
    expired = []
    def _mutator(doc):
        for c in doc["claims"]:
            if c.get("state") == "claimed" and _is_claim_expired(c):
                c["state"] = "expired"
                expired.append(copy_deep(c))
        return doc
    storage.modify_claims(_mutator)
    return expired


def copy_deep(obj):
    return copy.deepcopy(obj)


class ClaimConflictError(RuntimeError):
    """Raised when a target is already actively claimed by another attempt."""
