"""Atomic workspace storage for the Work Registry and suppressions."""

from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from api.webui import workspace

from .models import (
    REGISTRY_VERSION,
    public_document,
    validate_registry_document,
    validate_suppressions,
)


_LOCK = threading.RLock()
REGISTRY_FILENAME = "registry.v1.json"
SUPPRESSIONS_FILENAME = "suppressions.v1.json"


def _empty_registry() -> dict:
    return {"version": REGISTRY_VERSION, "updated_at": _now(), "jobs": []}


def _empty_suppressions() -> dict:
    return {"version": REGISTRY_VERSION, "items": []}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _root() -> Path | None:
    value = workspace.workspace_root()
    return Path(value) if value else None


def workbench_dir() -> Path | None:
    root = _root()
    return root / "_system" / "workbench" if root else None


def quarantine_dir() -> Path | None:
    directory = workbench_dir()
    return directory / "quarantine" if directory else None


def _path(filename: str) -> Path | None:
    directory = workbench_dir()
    return directory / filename if directory else None


def _quarantine(path: Path) -> None:
    if not path.exists():
        return
    target_dir = quarantine_dir()
    if target_dir is None:
        return
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = target_dir / f"{path.name}.{stamp}.corrupt"
    try:
        shutil.move(str(path), str(target))
    except OSError:
        pass


def _read(path: Path | None, empty_factory, validator):
    if path is None or not path.is_file():
        return empty_factory()
    try:
        with path.open(encoding="utf-8") as handle:
            document = json.load(handle)
        validator(document)
        return copy.deepcopy(document)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        with _LOCK:
            _quarantine(path)
        return empty_factory()


def _atomic_write(path: Path, document: dict, validator) -> None:
    validator(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(document, indent=2, ensure_ascii=False).encode("utf-8")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def read_registry() -> dict:
    with _LOCK:
        return _read(_path(REGISTRY_FILENAME), _empty_registry, validate_registry_document)


def write_registry(document: dict) -> dict:
    root = _root()
    if root is None:
        return {"ok": False, "error": "workspace_not_configured"}
    validate_registry_document(document)
    safe_document = public_document(document)
    with _LOCK:
        _atomic_write(_path(REGISTRY_FILENAME), safe_document, validate_registry_document)
    return {"ok": True}


def read_suppressions() -> dict:
    with _LOCK:
        return _read(_path(SUPPRESSIONS_FILENAME), _empty_suppressions, validate_suppressions)


def write_suppressions(document: dict) -> dict:
    if _root() is None:
        return {"ok": False, "error": "workspace_not_configured"}
    validate_suppressions(document)
    with _LOCK:
        _atomic_write(_path(SUPPRESSIONS_FILENAME), copy.deepcopy(document), validate_suppressions)
    return {"ok": True}
