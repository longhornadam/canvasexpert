"""Immutable receipt creation and safe list/detail projections."""

import copy
import secrets
from datetime import datetime, timezone

from . import storage


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_receipt(*, subject_type: str, subject_id: str, kind: str, status: str,
                targets: list, **extra) -> dict:
    now = _now()
    return {
        "version": 1,
        "receipt_id": secrets.token_urlsafe(18),
        "subject_type": subject_type,
        "subject_id": str(subject_id),
        "kind": kind,
        "attempted_at": now,
        "completed_at": now,
        "status": status,
        "targets": copy.deepcopy(targets),
        **copy.deepcopy(extra),
    }


def create_receipt(receipt: dict) -> dict:
    return storage.append_receipt(receipt)


def list_receipts() -> list[dict]:
    document = storage.read_document()
    output = []
    for receipt in reversed(document["receipts"]):
        output.append({
            "receipt_id": receipt["receipt_id"],
            "subject_type": receipt["subject_type"],
            "subject_id": receipt["subject_id"],
            "kind": receipt["kind"],
            "status": receipt["status"],
            "attempted_at": receipt.get("attempted_at"),
            "completed_at": receipt.get("completed_at"),
            "target_count": len(receipt.get("targets") or []),
            "detail_url": f"/api/receipts/{receipt['receipt_id']}",
        })
    return output


def get_receipt(receipt_id: str) -> dict | None:
    return storage.find_receipt(receipt_id)
