from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import tester_license
from app.tester_license import (
    TESTER_LICENSE_AUDIENCE,
    TESTER_LICENSE_SCHEMA_VERSION,
    TESTER_RELEASE_LABEL,
    TesterLicenseError,
    TesterLicenseMiddleware,
    TesterLicenseState,
    activate_tester_license,
    current_tester_license_status,
    verify_tester_license_token,
)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _keypair() -> tuple[Ed25519PrivateKey, str]:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return private, _b64url(public)


def _token(
    private: Ed25519PrivateKey,
    *,
    tester_id: str = "T001",
    release_label: str = TESTER_RELEASE_LABEL,
    not_before: datetime,
    expires_at: datetime,
) -> str:
    payload = {
        "schema_version": TESTER_LICENSE_SCHEMA_VERSION,
        "audience": TESTER_LICENSE_AUDIENCE,
        "license_id": str(uuid4()),
        "tester_id": tester_id,
        "release_label": release_label,
        "not_before_utc": not_before.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "expires_at_utc": expires_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"LR1.{_b64url(encoded)}.{_b64url(private.sign(encoded))}"


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 8, 24, 0, 0, tzinfo=timezone.utc)


def test_valid_signed_license_is_active(now: datetime) -> None:
    private, public = _keypair()
    token = _token(private, not_before=now - timedelta(minutes=1), expires_at=now + timedelta(days=7))

    status = verify_tester_license_token(token, now=now, public_key_b64=public)

    assert status.state == TesterLicenseState.ACTIVE
    assert status.active is True
    assert status.tester_id == "T001"
    assert status.release_label == TESTER_RELEASE_LABEL


def test_modified_signed_payload_is_rejected(now: datetime) -> None:
    private, public = _keypair()
    token = _token(private, not_before=now - timedelta(minutes=1), expires_at=now + timedelta(days=7))
    prefix, payload, signature = token.split(".")
    decoded = json.loads(base64.urlsafe_b64decode(payload + "=" * ((4 - len(payload) % 4) % 4)).decode("utf-8"))
    decoded["tester_id"] = "T999"
    modified = json.dumps(decoded, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    tampered = f"{prefix}.{_b64url(modified)}.{signature}"

    with pytest.raises(TesterLicenseError) as exc:
        verify_tester_license_token(tampered, now=now, public_key_b64=public)

    assert exc.value.state == TesterLicenseState.INVALID


def test_expired_license_fails_closed(now: datetime) -> None:
    private, public = _keypair()
    token = _token(private, not_before=now - timedelta(days=2), expires_at=now - timedelta(seconds=1))

    with pytest.raises(TesterLicenseError) as exc:
        verify_tester_license_token(token, now=now, public_key_b64=public)

    assert exc.value.state == TesterLicenseState.EXPIRED


def test_future_license_fails_closed(now: datetime) -> None:
    private, public = _keypair()
    token = _token(private, not_before=now + timedelta(minutes=5), expires_at=now + timedelta(days=7))

    with pytest.raises(TesterLicenseError) as exc:
        verify_tester_license_token(token, now=now, public_key_b64=public)

    assert exc.value.state == TesterLicenseState.NOT_YET_VALID


def test_wrong_release_license_fails_closed(now: datetime) -> None:
    private, public = _keypair()
    token = _token(
        private,
        release_label="0.8.0-rc3-tester2",
        not_before=now - timedelta(minutes=1),
        expires_at=now + timedelta(days=7),
    )

    with pytest.raises(TesterLicenseError) as exc:
        verify_tester_license_token(token, now=now, public_key_b64=public)

    assert exc.value.state == TesterLicenseState.WRONG_RELEASE


def test_activation_persists_under_runtime_and_reloads(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, now: datetime) -> None:
    private, public = _keypair()
    token = _token(private, not_before=now - timedelta(minutes=1), expires_at=now + timedelta(days=7))
    monkeypatch.setenv("LAW_RAG_TESTER_LICENSE_REQUIRED", "1")
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setattr(tester_license, "TESTER_LICENSE_PUBLIC_KEY_B64", public)

    activated = activate_tester_license(token, now=now)
    reloaded = current_tester_license_status(now=now)

    assert activated.active is True
    assert reloaded.active is True
    assert reloaded.tester_id == "T001"
    assert tester_license.tester_license_path() == tmp_path / "runtime" / "tester-license" / "license.txt"
    assert tester_license.tester_license_path().read_text(encoding="utf-8").strip() == token


def test_api_is_locked_until_license_activation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    live_now = datetime.now(timezone.utc).replace(microsecond=0)
    private, public = _keypair()
    token = _token(
        private,
        not_before=live_now - timedelta(minutes=1),
        expires_at=live_now + timedelta(days=7),
    )
    monkeypatch.setenv("LAW_RAG_TESTER_LICENSE_REQUIRED", "1")
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setattr(tester_license, "TESTER_LICENSE_PUBLIC_KEY_B64", public)

    inner = FastAPI()

    @inner.get("/api/private")
    def private_route() -> dict[str, bool]:
        return {"ok": True}

    @inner.get("/api/tester-license/status")
    def license_status() -> dict[str, str]:
        return {"state": current_tester_license_status().state.value}

    client = TestClient(TesterLicenseMiddleware(inner))

    locked = client.get("/api/private")
    allowed_status = client.get("/api/tester-license/status")
    activate_tester_license(token)
    unlocked = client.get("/api/private")

    assert locked.status_code == 423
    assert locked.json()["tester_license"]["state"] == "MISSING"
    assert allowed_status.status_code == 200
    assert unlocked.status_code == 200
    assert unlocked.json() == {"ok": True}


def test_source_contains_public_key_only() -> None:
    source = Path(tester_license.__file__).read_text(encoding="utf-8")
    assert "BEGIN PRIVATE KEY" not in source
    assert "BEGIN ED25519 PRIVATE KEY" not in source
    assert tester_license.TESTER_LICENSE_PUBLIC_KEY_B64 in source
