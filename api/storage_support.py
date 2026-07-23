"""Neutral atomic-file and cross-process lock primitives."""
from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from api.webui import workspace

UTC_COMPACT_STAMP_FORMAT = "%Y%m%dT%H%M%S%fZ"


def utc_compact_stamp() -> str:
    """Return a fresh, sortable UTC timestamp for internal backup/quarantine
    filenames -- the one shared format instead of each caller picking its own
    (or its own precision)."""
    return datetime.now(timezone.utc).strftime(UTC_COMPACT_STAMP_FORMAT)


def quarantine_corrupt_file(path: Path, target_dir: Path) -> None:
    """Move a corrupt document to *target_dir* as ``<name>.<stamp>.corrupt``.

    Best-effort: swallows OSError so a failed quarantine never blocks the
    caller's fallback to an empty document.
    """
    if not os.path.isfile(workspace.extended_path(str(path))):
        return
    os.makedirs(workspace.extended_path(str(target_dir)), exist_ok=True)
    target = Path(target_dir) / f"{Path(path).name}.{utc_compact_stamp()}.corrupt"
    try:
        shutil.move(workspace.extended_path(str(path)), workspace.extended_path(str(target)))
    except OSError:
        pass


def _replace_with_retry(source: str, target: str, *, attempts: int = 10) -> None:
    """os.replace, tolerant of transient Windows rename contention.

    Antivirus and the search indexer briefly open a just-closed file, so the
    replace can fail with WinError 5 (access denied) / 32 (sharing violation),
    both surfaced as PermissionError. These clear in milliseconds — retry a few
    times with a short backoff before giving up. Elsewhere it is a single call.
    """
    for attempt in range(attempts):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if os.name != "nt" or attempt == attempts - 1:
                raise
            time.sleep(0.02 * (attempt + 1))


_REGISTRY_LOCK = threading.Lock()
_LOCAL_LOCKS: dict[str, threading.RLock] = {}
_THREAD_STATE = threading.local()


def _held_paths() -> set[str]:
    paths = getattr(_THREAD_STATE, "held_paths", None)
    if paths is None:
        paths = set()
        _THREAD_STATE.held_paths = paths
    return paths


def _local_lock(key: str) -> threading.RLock:
    with _REGISTRY_LOCK:
        return _LOCAL_LOCKS.setdefault(key, threading.RLock())


@contextmanager
def interprocess_lock(lock_path: Path):
    """Acquire a thread- and process-safe adjacent-byte lock."""
    target = Path(lock_path).resolve()
    key = os.path.abspath(str(target))
    local_lock = _local_lock(key)
    local_lock.acquire()
    held = _held_paths()
    handle = None
    acquired_os_lock = key not in held
    os_lock_acquired = False
    try:
        if acquired_os_lock:
            # os-level via extended_path: pathlib strips the \\?\ prefix, so a
            # deep lock path (e.g. mirror tree) would otherwise fail past 260.
            os.makedirs(workspace.extended_path(str(target.parent)), exist_ok=True)
            handle = open(workspace.extended_path(str(target)), "a+b")
            if os.stat(workspace.extended_path(str(target))).st_size == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            os_lock_acquired = True
            held.add(key)
        yield
    finally:
        if acquired_os_lock:
            if os_lock_acquired:
                held.discard(key)
            try:
                if handle is not None and os_lock_acquired:
                    if os.name == "nt":
                        import msvcrt
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                if handle is not None:
                    handle.close()
        local_lock.release()


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Flush a same-directory temporary file, then atomically replace target."""
    target = Path(path)
    # os-level via extended_path so deep targets (mirror/catalog trees) survive
    # Windows' 260-char limit; mkstemp(dir=extended) yields an already-prefixed
    # temporary, so os.replace/os.unlink below inherit long-path safety.
    os.makedirs(workspace.extended_path(str(target.parent)), exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{target.name}-", suffix=".tmp", dir=workspace.extended_path(str(target.parent))
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _replace_with_retry(temporary, workspace.extended_path(str(target)))
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


def atomic_write_json(path: Path, document: dict) -> None:
    if not isinstance(document, dict):
        raise TypeError("document must be a dict")
    import json

    atomic_write_bytes(
        Path(path), json.dumps(document, indent=2, ensure_ascii=False).encode("utf-8")
    )
