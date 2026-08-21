from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.runtime_encryption as runtime_encryption
from app.main import app
from app.runtime_encryption import (
    RuntimeEncryptionRequiredError,
    apply_runtime_encryption,
    runtime_encryption_overview,
    set_runtime_encryption_mode,
)
from app.runtime_encryption_models import RuntimeEncryptionMode, RuntimeEncryptionState


def test_auto_is_explicitly_unsupported_off_windows(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.delenv("LAW_RAG_RUNTIME_ENCRYPTION_MODE", raising=False)
    monkeypatch.setattr(runtime_encryption.sys, "platform", "linux")

    overview = apply_runtime_encryption(RuntimeEncryptionMode.AUTO)

    assert overview.state == RuntimeEncryptionState.UNSUPPORTED
    assert overview.protected_root_names == []
    assert set(overview.unprotected_root_names) == {"jobs", "uploads", "rendered", "batches", "cleanup", "exports"}
    assert overview.shared_legal_managed is False


def test_required_fails_closed_off_windows(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(runtime_encryption.sys, "platform", "linux")

    with pytest.raises(RuntimeEncryptionRequiredError):
        apply_runtime_encryption(RuntimeEncryptionMode.REQUIRED)


def test_mock_windows_efs_encrypts_only_managed_private_roots(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(runtime_encryption.sys, "platform", "win32")
    legal = tmp_path / "legal" / "legal.db"
    legal.parent.mkdir(parents=True)
    legal.write_text("PUBLIC-LEGAL", encoding="utf-8")
    existing = tmp_path / "jobs" / "job-a" / "artifact.json"
    existing.parent.mkdir(parents=True)
    existing.write_text("private", encoding="utf-8")

    encrypted: set[Path] = set()

    def fake_status(path: Path):
        return (runtime_encryption.FILE_IS_ENCRYPTED if path.resolve() in encrypted else runtime_encryption.FILE_ENCRYPTABLE), None

    def fake_encrypt(path: Path):
        encrypted.add(path.resolve())

    monkeypatch.setattr(runtime_encryption, "_status", fake_status)
    monkeypatch.setattr(runtime_encryption, "_encrypt", fake_encrypt)

    overview = apply_runtime_encryption(RuntimeEncryptionMode.AUTO)

    assert overview.state == RuntimeEncryptionState.ENCRYPTED
    assert set(overview.protected_root_names) == {"jobs", "uploads", "rendered", "batches", "cleanup", "exports"}
    assert existing.resolve() in encrypted
    assert legal.resolve() not in encrypted
    assert legal.read_text(encoding="utf-8") == "PUBLIC-LEGAL"


def test_symlink_in_managed_tree_never_becomes_a_protected_claim(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(runtime_encryption.sys, "platform", "win32")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("outside", encoding="utf-8")
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    (jobs / "escape").symlink_to(outside, target_is_directory=True)

    encrypted: set[Path] = set()

    def fake_status(path: Path):
        return (runtime_encryption.FILE_IS_ENCRYPTED if path.resolve() in encrypted else runtime_encryption.FILE_ENCRYPTABLE), None

    monkeypatch.setattr(runtime_encryption, "_status", fake_status)
    monkeypatch.setattr(runtime_encryption, "_encrypt", lambda path: encrypted.add(path.resolve()))

    overview = apply_runtime_encryption(RuntimeEncryptionMode.AUTO)

    assert overview.state == RuntimeEncryptionState.DEGRADED
    assert "jobs" in overview.unprotected_root_names
    assert (outside / "secret.txt").read_text(encoding="utf-8") == "outside"
    assert (outside / "secret.txt").resolve() not in encrypted


def test_off_policy_never_decrypts_existing_content(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(runtime_encryption.sys, "platform", "win32")
    path = tmp_path / "jobs"
    path.mkdir()
    encrypted = {path.resolve()}
    monkeypatch.setattr(
        runtime_encryption,
        "_status",
        lambda target: (runtime_encryption.FILE_IS_ENCRYPTED if target.resolve() in encrypted else runtime_encryption.FILE_ENCRYPTABLE, None),
    )
    monkeypatch.setattr(runtime_encryption, "_encrypt", lambda _path: (_ for _ in ()).throw(AssertionError("OFF must not encrypt")))

    overview = apply_runtime_encryption(RuntimeEncryptionMode.OFF)

    assert overview.state == RuntimeEncryptionState.DISABLED
    assert path.exists()


def test_mode_persistence_and_status_api_are_non_secret(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.delenv("LAW_RAG_RUNTIME_ENCRYPTION_MODE", raising=False)
    monkeypatch.setattr(runtime_encryption.sys, "platform", "linux")

    saved = set_runtime_encryption_mode(RuntimeEncryptionMode.AUTO)
    loaded = runtime_encryption_overview()
    client = TestClient(app)
    api = client.get("/api/runtime/encryption")

    assert saved.state == RuntimeEncryptionState.UNSUPPORTED
    assert loaded.mode == RuntimeEncryptionMode.AUTO
    assert api.status_code == 200
    assert api.json()["mode"] == "AUTO"
    config_text = (tmp_path / "config" / "runtime-security.json").read_text(encoding="utf-8")
    assert "AUTO" in config_text
    assert "api_key" not in config_text.lower()


def test_required_api_rejects_unsupported_platform_without_persisting_required(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.delenv("LAW_RAG_RUNTIME_ENCRYPTION_MODE", raising=False)
    monkeypatch.setattr(runtime_encryption.sys, "platform", "linux")
    client = TestClient(app)

    response = client.put("/api/runtime/encryption", json={"mode": "REQUIRED"})

    assert response.status_code == 409
    config = tmp_path / "config" / "runtime-security.json"
    assert not config.exists() or "REQUIRED" not in config.read_text(encoding="utf-8")
