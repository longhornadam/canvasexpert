"""Neutral atomic-file and cross-process lock primitives."""
from __future__ import annotations

import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path


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
            target.parent.mkdir(parents=True, exist_ok=True)
            handle = target.open("a+b")
            if target.stat().st_size == 0:
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
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{target.name}-", suffix=".tmp", dir=str(target.parent)
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
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
