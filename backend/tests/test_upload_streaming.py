from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.upload_streaming as upload_streaming
from app.upload_streaming import (
    CHUNK_SIZE,
    MAX_UPLOAD_BYTES,
    UploadInsufficientStorageError,
    UploadTooLargeError,
    ensure_upload_capacity,
    stream_upload_to_path,
)


class FakeUpload:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.offset = 0
        self.read_sizes: list[int] = []

    async def read(self, size: int) -> bytes:
        self.read_sizes.append(size)
        chunk = self.payload[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk


def test_stage12c_declares_exact_500_mib_limit() -> None:
    assert MAX_UPLOAD_BYTES == 500 * 1024 * 1024
    assert CHUNK_SIZE == 1024 * 1024


def test_stream_upload_reads_fixed_chunks_and_persists_exact_bytes(tmp_path: Path) -> None:
    payload = b"%PDF-1.7\n" + b"x" * (CHUNK_SIZE * 2 + 123)
    upload = FakeUpload(payload)
    destination = tmp_path / "uploads" / "job" / "source.pdf"

    size, header = asyncio.run(stream_upload_to_path(upload, destination))

    assert size == len(payload)
    assert header.startswith(b"%PDF-")
    assert destination.read_bytes() == payload
    assert upload.read_sizes
    assert all(size == CHUNK_SIZE for size in upload.read_sizes)


def test_stream_upload_removes_partial_file_when_limit_is_crossed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(upload_streaming, "MAX_UPLOAD_BYTES", CHUNK_SIZE + 16)
    payload = b"%PDF-1.7\n" + b"x" * (CHUNK_SIZE * 2)
    upload = FakeUpload(payload)
    destination = tmp_path / "uploads" / "job" / "source.pdf"

    with pytest.raises(UploadTooLargeError):
        asyncio.run(stream_upload_to_path(upload, destination))

    assert not destination.exists()
    assert not destination.parent.exists()


def test_disk_preflight_requires_file_plus_safety_reserve(tmp_path: Path, monkeypatch) -> None:
    expected_size = 300 * 1024 * 1024
    required = expected_size + upload_streaming.UPLOAD_DISK_RESERVE_BYTES
    monkeypatch.setattr(
        upload_streaming.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(total=required, used=1, free=required - 1),
    )

    with pytest.raises(UploadInsufficientStorageError):
        ensure_upload_capacity(tmp_path, expected_size)


def test_declared_oversize_is_rejected_before_disk_write(tmp_path: Path) -> None:
    with pytest.raises(UploadTooLargeError):
        ensure_upload_capacity(tmp_path, MAX_UPLOAD_BYTES + 1)
