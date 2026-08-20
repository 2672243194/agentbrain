from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_STALE_SECONDS = 60.0
_RETRY_INTERVAL = 0.05

_local = threading.local()


class VaultLockTimeout(RuntimeError):
    pass


@contextmanager
def vault_lock(root: Path, timeout: float = 10.0) -> Iterator[None]:
    """Mutual exclusion for vault writes across processes and threads.

    Re-entrant within the same thread (nested calls from vault.save() inside
    an explicit vault.locked() transaction). Cross-process exclusion uses a
    lock file created atomically (O_CREAT|O_EXCL); if the holder crashed, the
    lock is considered stale after _STALE_SECONDS and reclaimed.
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

    deadline = time.monotonic() + timeout
    fd = -1
    while True:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            break
        except FileExistsError:
            if time.monotonic() > deadline:
                if _is_stale(lock):
                    try:
                        lock.unlink()
                    except OSError:
                        pass
                    deadline = time.monotonic() + timeout
                    continue
                raise VaultLockTimeout(
                    f"Could not acquire vault lock at '{lock}' within {timeout}s. "
                    "Another agent process may be stuck; delete the lock file to force."
                )
            time.sleep(_RETRY_INTERVAL)
    _local.held = [key, 1]
    try:
        yield
    finally:
        _local.held = None
        try:
            os.close(fd)
        finally:
            try:
                lock.unlink()
            except OSError:
                pass


def _is_stale(lock: Path) -> bool:
    try:
        return time.time() - lock.stat().st_mtime > _STALE_SECONDS
    except OSError:
        return False


def atomic_write(path: Path, text: str) -> None:
    """Write via temp file + atomic replace, so readers never see torn files."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
