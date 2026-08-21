from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_RETRY_INTERVAL = 0.05

_local = threading.local()

try:
    import msvcrt

    def _try_lock(fd: int) -> bool:
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _release(fd: int) -> None:
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass

except ImportError:  # POSIX
    import fcntl

    def _try_lock(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _release(fd: int) -> None:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass


class VaultLockTimeout(RuntimeError):
    pass


@contextmanager
def vault_lock(root: Path, timeout: float = 10.0) -> Iterator[None]:
    """Mutual exclusion for vault writes across processes and threads.

    Uses an OS-level byte-range lock on a lock file, so a crashed holder
    releases instantly — no stale detection and no reclaim race. Re-entrant
    within the same thread. The lock file persists on disk; removing it while
    a holder might exist would break exclusion, so it is never unlinked.
    """
    lock = root / "Case-Learnings" / ".vault.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    key = str(lock)
    held = getattr(_local, "held", None)
    if held is not None and held[0] == key:
        held[1] += 1
        try:
            yield
        finally:
            held[1] -= 1
        return

    fd = os.open(str(lock), os.O_CREAT | os.O_RDWR)
    deadline = time.monotonic() + timeout
    try:
        while not _try_lock(fd):
            if time.monotonic() > deadline:
                raise VaultLockTimeout(
                    f"Could not acquire vault lock at '{lock}' within {timeout}s. "
                    "Another process is writing to this vault; the lock releases "
                    "automatically when that process exits."
                )
            time.sleep(_RETRY_INTERVAL)
        _local.held = [key, 1]
        try:
            yield
        finally:
            _local.held = None
            _release(fd)
    finally:
        os.close(fd)


def atomic_write(path: Path, text: str) -> None:
    """Write via temp file + atomic replace, so readers never see torn files."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
