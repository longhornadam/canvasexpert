"""Small cross-process lock for the machine-local operation ledger."""

import os
import threading
from contextlib import contextmanager
from pathlib import Path


_LOCAL = threading.local()


def _held_paths() -> set[str]:
    held = getattr(_LOCAL, "held_paths", None)
    if held is None:
        held = set()
        _LOCAL.held_paths = held
    return held


@contextmanager
def interprocess_lock(path: Path):
    """Hold one adjacent OS lock byte until the context exits.

    ``msvcrt.locking`` is used on Windows and ``fcntl.flock`` on POSIX.  The
    thread-local re-entry guard keeps nested storage helpers inside one ledger
    transaction from trying to lock the same byte twice.
    """
    target = Path(path)
    key = os.path.abspath(str(target))
    held = _held_paths()
    if key in held:
        yield
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a+b") as handle:
        handle.seek(0)
        if handle.tell() == 0 and target.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        held.add(key)
        try:
            yield
        finally:
            held.discard(key)
            try:
                if os.name == "nt":
                    import msvcrt
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()
