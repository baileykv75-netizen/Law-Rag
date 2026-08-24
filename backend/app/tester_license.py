from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel
from starlette.responses import JSONResponse

from .safe_persistence import atomic_write_text
from .storage import runtime_dir

TESTER_LICENSE_SCHEMA_VERSION = "1.0.0"
TESTER_LICENSE_AUDIENCE = "law-rag-limited-test"
TESTER_RELEASE_LABEL = "0.8.0-rc3-tester2"
TESTER_LICENSE_PUBLIC_KEY_B64 = "JYVGx5sCRLFW8PGLWiVZMwxM3QZx9bshcep0rH6uTKQ"
TESTER_LICENSE_TOKEN_PREFIX = "LR1"
_TESTER_LICENSE_REQUIRED_ENV = "LAW_RAG_TESTER_LICENSE_REQUIRED"


class TesterLicenseState(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    MISSING = "MISSING"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    NOT_YET_VALID = "NOT_YET_VALID"
    WRONG_RELEASE = "WRONG_RELEASE"
    INVALID = "INVALID"


class TesterLicenseStatus(BaseModel):
    required: bool
    state: TesterLicenseState
    active: bool
    tester_id: str | None = None
    license_id: str | None = None
    release_label: str | None = None
    not_before_utc: datetime | None = None
    expires_at_utc: datetime | None = None
    detail: str


class TesterLicenseActivationRequest(BaseModel):
    token: str


class TesterLicenseError(ValueError):
    def __init__(self, state: TesterLicenseState, detail: str) -> None:
        super().__init__(detail)
        self.state = state
        self.detail = detail


def tester_license_required() -> bool:
    return os.getenv(_TESTER_LICENSE_REQUIRED_ENV, "").strip() == "1"


def tester_license_dir() -> Path:
    return runtime_dir() / "tester-license"


def tester_license_path() -> Path:
    return tester_license_dir() / "license.txt"


def _b64url_decode(value: str) -> bytes:
    if not value or any(character.isspace() for character in value):
        raise ValueError("base64url segment is empty or contains whitespace")
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _parse_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{field} must be an RFC3339 UTC timestamp ending in Z")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _status_from_error(required: bool, error: TesterLicenseError) -> TesterLicenseStatus:
    return TesterLicenseStatus(
        required=required,
        state=error.state,
        active=False,
        detail=error.detail,
    )


def verify_tester_license_token(
    token: str,
    *,
    now: datetime | None = None,
    public_key_b64: str | None = None,
    expected_release_label: str = TESTER_RELEASE_LABEL,
) -> TesterLicenseStatus:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    compact = token.strip()
    parts = compact.split(".")
    if len(parts) != 3 or parts[0] != TESTER_LICENSE_TOKEN_PREFIX:
        raise TesterLicenseError(TesterLicenseState.INVALID, "许可证格式无效。")

    try:
        payload_bytes = _b64url_decode(parts[1])
        signature = _b64url_decode(parts[2])
        public_key_bytes = _b64url_decode(public_key_b64 or TESTER_LICENSE_PUBLIC_KEY_B64)
        if len(public_key_bytes) != 32:
            raise ValueError("Ed25519 public key must contain 32 bytes")
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(signature, payload_bytes)
    except InvalidSignature as exc:
        raise TesterLicenseError(TesterLicenseState.INVALID, "许可证签名无效或内容已被修改。") from exc
    except Exception as exc:
        raise TesterLicenseError(TesterLicenseState.INVALID, "许可证无法解析或验证。") from exc

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        required_fields = {
            "schema_version",
            "audience",
            "license_id",
            "tester_id",
            "release_label",
            "not_before_utc",
            "expires_at_utc",
        }
        if set(payload) != required_fields:
            raise ValueError("payload fields do not match the licensed schema")
        if payload["schema_version"] != TESTER_LICENSE_SCHEMA_VERSION:
            raise ValueError("unsupported tester license schema")
        if payload["audience"] != TESTER_LICENSE_AUDIENCE:
            raise ValueError("wrong tester license audience")
        if not isinstance(payload["license_id"], str) or not payload["license_id"].strip():
            raise ValueError("license_id must be non-empty")
        tester_id = payload["tester_id"]
        if not isinstance(tester_id, str) or not tester_id.strip() or len(tester_id) > 64:
            raise ValueError("tester_id must be a non-empty string up to 64 chars")
        release_label = payload["release_label"]
        if not isinstance(release_label, str) or not release_label.strip():
            raise ValueError("release_label must be non-empty")
        not_before = _parse_utc(payload["not_before_utc"], "not_before_utc")
        expires_at = _parse_utc(payload["expires_at_utc"], "expires_at_utc")
        if expires_at <= not_before:
            raise ValueError("expires_at_utc must be after not_before_utc")
    except TesterLicenseError:
        raise
    except Exception as exc:
        raise TesterLicenseError(TesterLicenseState.INVALID, "许可证内容结构无效。") from exc

    if release_label != expected_release_label:
        raise TesterLicenseError(
            TesterLicenseState.WRONG_RELEASE,
            f"许可证适用于 {release_label}，当前测试包需要 {expected_release_label}。",
        )
    if current < not_before:
        raise TesterLicenseError(TesterLicenseState.NOT_YET_VALID, "许可证尚未到生效时间。")
    if current >= expires_at:
        raise TesterLicenseError(TesterLicenseState.EXPIRED, "许可证已过期。")

    return TesterLicenseStatus(
        required=True,
        state=TesterLicenseState.ACTIVE,
        active=True,
        tester_id=tester_id.strip(),
        license_id=payload["license_id"],
        release_label=release_label,
        not_before_utc=not_before,
        expires_at_utc=expires_at,
        detail="测试许可证有效。",
    )


def activate_tester_license(token: str, *, now: datetime | None = None) -> TesterLicenseStatus:
    status = verify_tester_license_token(token, now=now)
    atomic_write_text(tester_license_path(), token.strip() + "\n")
    return status


def current_tester_license_status(*, now: datetime | None = None) -> TesterLicenseStatus:
    required = tester_license_required()
    if not required:
        return TesterLicenseStatus(
            required=False,
            state=TesterLicenseState.NOT_REQUIRED,
            active=True,
            detail="当前构建未启用测试许可证门禁。",
        )
    path = tester_license_path()
    if not path.is_file():
        return TesterLicenseStatus(
            required=True,
            state=TesterLicenseState.MISSING,
            active=False,
            detail="尚未激活测试许可证。",
        )
    try:
        token = path.read_text(encoding="utf-8").strip()
        return verify_tester_license_token(token, now=now)
    except TesterLicenseError as exc:
        return _status_from_error(True, exc)
    except OSError:
        return TesterLicenseStatus(
            required=True,
            state=TesterLicenseState.INVALID,
            active=False,
            detail="本机测试许可证无法读取。",
        )


class TesterLicenseMiddleware:
    _ALLOWED_PREFIXES = (
        "/api/health",
        "/api/tester-license/status",
        "/api/tester-license/activate",
    )

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http" or not tester_license_required():
            await self.app(scope, receive, send)
            return
        path = str(scope.get("path") or "")
        if not path.startswith("/api/") or any(path == allowed for allowed in self._ALLOWED_PREFIXES):
            await self.app(scope, receive, send)
            return
        status = current_tester_license_status()
        if status.active:
            await self.app(scope, receive, send)
            return
        response = JSONResponse(
            status_code=423,
            content={
                "detail": "Law-Rag 限量测试许可证未激活或无效。",
                "tester_license": status.model_dump(mode="json"),
            },
        )
        await response(scope, receive, send)
