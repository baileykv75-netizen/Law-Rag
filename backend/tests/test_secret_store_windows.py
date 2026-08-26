from __future__ import annotations

import os
import sys

import pytest

from app.secret_store import (
    SecretStoreError,
    delete_secure_secret,
    read_secure_secret,
    resolve_provider_secret,
    write_secure_secret,
)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Credential Manager smoke")
def test_windows_credential_manager_round_trip(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    secret = "law-rag-stage12d-synthetic-secret"
    delete_secure_secret("deepseek")
    try:
        try:
            write_secure_secret("deepseek", secret)
        except SecretStoreError as exc:
            if "error 1312" in str(exc):
                pytest.skip("Windows Credential Manager is unavailable in this session.")
            raise
        assert read_secure_secret("deepseek") == secret
        resolved = resolve_provider_secret("deepseek")
        assert resolved.value == secret
        assert resolved.source == "windows_credential_manager"
    finally:
        delete_secure_secret("deepseek")
    assert read_secure_secret("deepseek") is None
