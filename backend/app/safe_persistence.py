from __future__ import annotations

import errno
import os
import tempfile
import threading
import time
from pathlib import Path


class AtomicWriteError(RuntimeError):
    pass


_PATH_LOCKS: dict[str, threading.RLock] = {}
_PATH_LOCKS_GUARD = threading.RLock()
_DEFAULT_IO_ATTEMPTS = 8
_DEFAULT_BASE_DELAY_SECONDS = 0.025


def _lock_for(path: Path) -> threading.RLock:
    key = str(path.absolute())
    with _PATH_LOCKS_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _PATH_LOCKS[key] = lock
        return lock


def _retryable_os_error(exc: OSError) -> bool:
    # Windows sharing/access violations commonly surface as winerror 5/32/33.
    # Antivirus/indexers can also create brief EACCES/EPERM/EBUSY windows.
    winerror = getattr(exc, "winerror", None)
    if winerror in {5, 32, 33}:
        return True
    return exc.errno in {errno.EACCES, errno.EPERM, errno.EBUSY}


def _sleep_before_retry(attempt: int, base_delay: float) -> None:
    # Small bounded exponential backoff. The maximum delay stays below one second
    # so a transient Windows sharing violation does not become user-visible latency.
    time.sleep(min(base_delay * (2 ** max(0, attempt - 1)), 0.4))


def read_text_with_retry(
    path: Path,
    *,
    encoding: str = "utf-8",
    attempts: int = _DEFAULT_IO_ATTEMPTS,
    base_delay_seconds: float = _DEFAULT_BASE_DELAY_SECONDS,
) -> str:
    """Read a text artifact while coordinating with in-process atomic writers.

    The per-path lock prevents API polling threads from racing a pipeline writer in
    the same Law-Rag process. A bounded OS-level retry additionally tolerates short
    Windows sharing violations caused by antivirus/indexing or filesystem timing.
    """

    last_error: OSError | None = None
    with _lock_for(path):
        for attempt in range(1, attempts + 1):
            try:
                return path.read_text(encoding=encoding)
            except OSError as exc:
                last_error = exc
                if attempt >= attempts or not _retryable_os_error(exc):
                    raise
                _sleep_before_retry(attempt, base_delay_seconds)
    assert last_error is not None
    raise last_error


def atomic_write_text(
    path: Path,
    content: str,
    *,
    encoding: str = "utf-8",
    errors: str | None = None,
    newline: str | None = None,
    attempts: int = _DEFAULT_IO_ATTEMPTS,
    base_delay_seconds: float = _DEFAULT_BASE_DELAY_SECONDS,
) -> None:
    """Atomically replace a text artifact while preserving the prior valid file.

    Writes to the same path are serialized inside the Law-Rag process. The final
    ``os.replace`` is retried with bounded exponential backoff for transient Windows
    sharing/access violations. Serialization happens before replacement, and a failed
    replacement never deletes the previous destination file.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    with _lock_for(path):
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding=encoding,
                errors=errors,
                newline=newline,
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())

            last_error: OSError | None = None
            for attempt in range(1, attempts + 1):
                try:
                    os.replace(temp_path, path)
                    temp_path = None
                    return
                except OSError as exc:
                    last_error = exc
                    if attempt >= attempts or not _retryable_os_error(exc):
                        raise
                    _sleep_before_retry(attempt, base_delay_seconds)

            assert last_error is not None
            raise last_error
        except Exception as exc:
            raise AtomicWriteError(
                f"Atomic write failed for {path.name}: {type(exc).__name__}"
            ) from exc
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
