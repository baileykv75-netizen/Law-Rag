from __future__ import annotations

import errno
import os
import shutil
from pathlib import Path
from typing import Any

CHUNK_SIZE = 1024 * 1024
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
UPLOAD_DISK_RESERVE_BYTES = 512 * 1024 * 1024


class UploadStreamError(RuntimeError):
    pass


class UploadTooLargeError(UploadStreamError):
    pass


class UploadInsufficientStorageError(UploadStreamError):
    pass


def declared_upload_size(upload: Any) -> int | None:
    """Return the multipart parser's known file size when available.

    FastAPI/Starlette UploadFile exposes ``size`` on current supported versions,
    but this helper deliberately tolerates older/custom UploadFile-like objects.
    The streamed byte counter remains the authoritative size guard.
    """

    value = getattr(upload, "size", None)
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _existing_disk_probe(path: Path) -> Path:
    probe = path.expanduser().resolve()
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    return probe


def ensure_upload_capacity(runtime_root: Path, expected_size: int | None) -> None:
    if expected_size is not None and expected_size > MAX_UPLOAD_BYTES:
        raise UploadTooLargeError("File exceeds the 500 MiB per-file limit.")

    # Keep a conservative post-upload reserve because downstream PDF rendering,
    # OCR evidence and reports also need writable local storage. This is only an
    # upload preflight, not a promise that every future OCR workload fits.
    upload_bytes = expected_size if expected_size is not None else MAX_UPLOAD_BYTES
    required_free = upload_bytes + UPLOAD_DISK_RESERVE_BYTES
    probe = _existing_disk_probe(runtime_root)
    try:
        free = shutil.disk_usage(probe).free
    except OSError as exc:
        raise UploadInsufficientStorageError(
            "Local disk capacity could not be checked safely before upload."
        ) from exc

    if free < required_free:
        raise UploadInsufficientStorageError(
            "Insufficient local disk space for this upload. Law-Rag requires the file size plus a 512 MiB safety reserve."
        )


def _cleanup_partial(destination: Path) -> None:
    try:
        destination.unlink(missing_ok=True)
    except OSError:
        pass
    try:
        destination.parent.rmdir()
    except OSError:
        pass


async def stream_upload_to_path(upload: Any, destination: Path) -> tuple[int, bytes]:
    """Copy an UploadFile-like object to disk without buffering the whole file.

    The source is consumed in fixed 1 MiB chunks. The destination is removed on
    limit, storage or write failure so another file/job in the batch is not
    contaminated by a partial source artifact.
    """

    destination.parent.mkdir(parents=True, exist_ok=True)
    size_bytes = 0
    header = b""

    try:
        with destination.open("wb") as handle:
            while True:
                chunk = await upload.read(CHUNK_SIZE)
                if not chunk:
                    break
                if not header:
                    header = chunk[:16]
                size_bytes += len(chunk)
                if size_bytes > MAX_UPLOAD_BYTES:
                    raise UploadTooLargeError("File exceeds the 500 MiB per-file limit.")
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
    except UploadTooLargeError:
        _cleanup_partial(destination)
        raise
    except OSError as exc:
        _cleanup_partial(destination)
        if exc.errno in {errno.ENOSPC, getattr(errno, "EDQUOT", -1)}:
            raise UploadInsufficientStorageError(
                "Local disk space was exhausted while writing the upload. The partial file was removed."
            ) from exc
        raise UploadStreamError(f"Could not persist uploaded file: {type(exc).__name__}.") from exc
    except Exception:
        _cleanup_partial(destination)
        raise

    return size_bytes, header
