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

    Raises ``ClaimConflictError`` if the target is already actively claimed
    by another process/attempt with a non-expired lease.
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
            if existing.get("state") != "claimed":
                continue
            if not _is_claim_expired(existing):
                raise ClaimConflictError(
                    f"target {target_key} is already actively claimed")
            # Expired — mark it
            existing["state"] = "expired"
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


def _is_claim_expired(claim: dict) -> bool:
    """A claim is expired if its lease has passed, or if the owning process
    is gone (different PID, or same PID but different start time)."""
    lease_str = claim.get("lease_expires_at")
    if lease_str:
        try:
            lease_dt = datetime.fromisoformat(lease_str)
            if datetime.now(timezone.utc) > lease_dt:
                return True
        except (ValueError, TypeError):
            return True  # unparseable → treat as expired

    # Different PID → the process that held it is gone
    if claim.get("owner_pid") != os.getpid():
        return True

    # Same PID but different start time → the PID was reused by a new process
    if claim.get("owner_started_at") != _process_started_at():
        return True

    return False


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
