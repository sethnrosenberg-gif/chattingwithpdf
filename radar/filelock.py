"""Tiny cross-process lock (O_EXCL lock file) for appends shared by parallel channel processes."""
from __future__ import annotations

import contextlib
import os
import time
from pathlib import Path


@contextlib.contextmanager
def locked(lock: Path, stale_after: float = 30.0):
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > stale_after:
                    lock.unlink(missing_ok=True)
            except (FileNotFoundError, PermissionError):
                pass
            time.sleep(0.05)
        except PermissionError:  # Windows: lock file mid-delete
            time.sleep(0.05)
    try:
        yield
    finally:
        for _ in range(20):
            try:
                lock.unlink(missing_ok=True)
                break
            except PermissionError:
                time.sleep(0.05)
