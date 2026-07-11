"""Batch (review snapshot) helpers — freeze reviews, compute digests, validate."""
import copy
import json

from . import models


def compute_review_digest(frozen_reviews: list[dict]) -> str:
    """Deterministic SHA-256 over the ordered list of frozen reviews."""
    canonical = json.dumps(
        frozen_reviews, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return models.sha256_hex(canonical)


def freeze_batch(operation_ids: list[str], frozen_reviews_by_op: dict[str, list[dict]]) -> dict:
    """Create a batch record for a set of operations.

    ``frozen_reviews_by_op`` maps operation_id → list of frozen review dicts.
    Returns a batch dict with batch_id, review_digest, frozen_reviews, created_at.
    """
    batch_id = models.new_batch_id()
    all_frozen = []
    for op_id in operation_ids:
        all_frozen.extend(frozen_reviews_by_op.get(op_id, []))
    digest = compute_review_digest(all_frozen)
    return models.new_batch(
        batch_id=batch_id,
        review_digest=digest,
        frozen_reviews=all_frozen,
    )


def validate_apply(operation: dict, batch_id: str, review_digest: str) -> bool:
    """Return True if the stored batch matches the apply request."""
    review = operation.get("review")
    if review is None:
        return False
    if review.get("batch_id") != batch_id:
        return False
    if review.get("review_digest") != review_digest:
        return False
    return True
