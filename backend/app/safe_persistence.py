from __future__ import annotations

import os
import tempfile
from pathlib import Path


class AtomicWriteError(RuntimeError):
    pass


def atomic_write_text(
    path: Path,
    content: str,
    *,
    encoding: str = "utf-8",
    errors: str | None = None,
    newline: str | None = None,
) -> None:
    """Atomically replace a text artifact while preserving any previous valid file on failure.

    Serialization should happen before calling this function. The temporary file is created in the
    destination directory so os.replace stays on the same filesystem. Failed temporary files are
    cleaned up best-effort; the existing destination is never unlinked by this helper.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
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
        os.replace(temp_path, path)
        temp_path = None
    except Exception as exc:
        raise AtomicWriteError(f"Atomic write failed for {path.name}: {type(exc).__name__}") from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
