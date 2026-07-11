"""Validated, atomic, machine-local receipt storage."""

import copy
import json
import os
import shutil
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import paths


VERSION = 1
_LOCK = threading.RLock()


@contextmanager
def storage_lock():
    """Hold the process-wide lock used by all operation-ledger storage."""
    with _LOCK:
        yield


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Write bytes through a flushed, same-directory atomic replacement."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{target.name}-", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            fd = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except Exception:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def atomic_write_json(path: Path, document: dict) -> None:
    """Serialize a JSON object and write it through ``atomic_write_bytes``."""
    if not isinstance(document, dict):
        raise TypeError("document must be a dict")
    payload = json.dumps(document, indent=2, ensure_ascii=False).encode("utf-8")
    atomic_write_bytes(Path(path), payload)


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
    atomic_write_json(paths.receipts_file(), document)


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
