"""Validated, atomic, machine-local receipt storage."""

import copy
import json
import os
import shutil
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import paths


VERSION = 1
_LOCK = threading.RLock()


class ReceiptConflictError(ValueError):
    """Raised when an immutable receipt ID already exists."""


class ReceiptSchemaError(ValueError):
    """Raised when a receipt document does not match the supported schema."""


def _empty() -> dict:
    return {"version": VERSION, "receipts": []}


def _validate_receipt(receipt: dict) -> None:
    if not isinstance(receipt, dict) or receipt.get("version") != VERSION:
        raise ReceiptSchemaError("unsupported receipt schema")
    required = ("receipt_id", "subject_type", "subject_id", "kind", "status", "targets")
    if any(not isinstance(receipt.get(name), str) or not receipt.get(name) for name in required[:-1]):
        raise ReceiptSchemaError("receipt envelope is incomplete")
    if receipt.get("subject_type") not in ("operation", "routine"):
        raise ReceiptSchemaError("unsupported receipt subject")
    if receipt.get("status") not in ("applied", "partial", "failed", "blocked", "no_effect"):
        raise ReceiptSchemaError("unsupported receipt status")
    if not isinstance(receipt.get("targets"), list):
        raise ReceiptSchemaError("receipt targets must be a list")


def _validate_document(document: dict) -> None:
    if not isinstance(document, dict) or document.get("version") != VERSION:
        raise ReceiptSchemaError("unsupported receipt document version")
    if not isinstance(document.get("receipts"), list):
        raise ReceiptSchemaError("receipt document must contain a list")
    for receipt in document["receipts"]:
        _validate_receipt(receipt)


def _quarantine(path: Path) -> None:
    if not path.exists():
        return
    target_dir = paths.quarantine_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = target_dir / f"{path.name}.{stamp}.corrupt"
    try:
        shutil.move(str(path), str(target))
    except OSError:
        pass


def _read_unlocked() -> dict:
    path = paths.receipts_file()
    if not path.exists():
        return _empty()
    try:
        with path.open(encoding="utf-8") as handle:
            document = json.load(handle)
        _validate_document(document)
        return document
    except (OSError, ValueError, TypeError, json.JSONDecodeError, ReceiptSchemaError):
        _quarantine(path)
        return _empty()


def _atomic_write_unlocked(document: dict) -> None:
    _validate_document(document)
    target = paths.receipts_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".receipts-", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(document, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def read_document() -> dict:
    with _LOCK:
        return copy.deepcopy(_read_unlocked())


def append_receipt(receipt: dict) -> dict:
    with _LOCK:
        _validate_receipt(receipt)
        document = _read_unlocked()
        if any(item.get("receipt_id") == receipt["receipt_id"] for item in document["receipts"]):
            raise ReceiptConflictError("receipt ID already exists")
        document["receipts"].append(copy.deepcopy(receipt))
        _atomic_write_unlocked(document)
        return copy.deepcopy(receipt)


def find_receipt(receipt_id: str) -> dict | None:
    with _LOCK:
        document = _read_unlocked()
        for receipt in document["receipts"]:
            if receipt.get("receipt_id") == receipt_id:
                return copy.deepcopy(receipt)
        return None
