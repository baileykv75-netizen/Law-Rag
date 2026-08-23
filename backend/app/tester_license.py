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
TESTER_RELEASE_LABEL = "0.8.0-rc3-tester1"
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
    public_key_b64: str = TESTER_LICENSE_PUBLIC_KEY_B64,
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
        public_key_bytes = _b64url_decode(public_key_b64)
        if len(public_key_bytes) != 32:
            raise ValueError("Ed25519 public key must contain 32 bytes")
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(signature, payload_bytes)
    except InvalidSignature as exc:
        raise TesterLicenseError(TesterLicenseState.INVALID, "许可证签名无效或内容已被修改。") from exc
    except Exception as exc:
        raise TesterLicenseError(TesterLicenseState.INVALID, "许可证无法解析或验证。") from exc

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TesterLicenseError(TesterLicenseState.INVALID, "许可证载荷不是有效 JSON。") from exc

    required_fields = {
        "schema_version",
        "audience",
        "license_id",
        "tester_id",
        "release_label",
        "not_before_utc",
        "expires_at_utc",
    }
    if not isinstance(payload, dict) or set(payload) != required_fields:
        raise TesterLicenseError(TesterLicenseState.INVALID, "许可证字段集合无效。")
    if payload["schema_version"] != TESTER_LICENSE_SCHEMA_VERSION or payload["audience"] != TESTER_LICENSE_AUDIENCE:
        raise TesterLicenseError(TesterLicenseState.INVALID, "许可证用途或版本无效。")

    tester_id = payload["tester_id"]
    license_id = payload["license_id"]
    release_label = payload["release_label"]
    if not isinstance(tester_id, str) or not (1 <= len(tester_id) <= 64) or not all(
        character.isalnum() or character in "._-" for character in tester_id
    ):
        raise TesterLicenseError(TesterLicenseState.INVALID, "Tester ID 无效。")
    if not isinstance(license_id, str) or not (8 <= len(license_id) <= 128):
        raise TesterLicenseError(TesterLicenseState.INVALID, "License ID 无效。")
    if release_label != expected_release_label:
        raise TesterLicenseError(
            TesterLicenseState.WRONG_RELEASE,
            f"该许可证仅适用于 {release_label}，当前测试包为 {expected_release_label}。",
        )

    try:
        not_before = _parse_utc(payload["not_before_utc"], "not_before_utc")
        expires_at = _parse_utc(payload["expires_at_utc"], "expires_at_utc")
    except ValueError as exc:
        raise TesterLicenseError(TesterLicenseState.INVALID, str(exc)) from exc
    if expires_at <= not_before:
        raise TesterLicenseError(TesterLicenseState.INVALID, "许可证有效期无效。")
    if current < not_before:
        raise TesterLicenseError(TesterLicenseState.NOT_YET_VALID, "许可证尚未到生效时间。")
    if current >= expires_at:
        raise TesterLicenseError(TesterLicenseState.EXPIRED, "许可证已过期，请向测试组织者获取新的许可证。")

    return TesterLicenseStatus(
        required=True,
        state=TesterLicenseState.ACTIVE,
        active=True,
        tester_id=tester_id,
        license_id=license_id,
        release_label=release_label,
        not_before_utc=not_before,
        expires_at_utc=expires_at,
        detail="测试许可证有效。",
    )


def current_tester_license_status(*, now: datetime | None = None) -> TesterLicenseStatus:
    required = tester_license_required()
    if not required:
        return TesterLicenseStatus(
            required=False,
            state=TesterLicenseState.NOT_REQUIRED,
            active=True,
            release_label=TESTER_RELEASE_LABEL,
            detail="当前运行模式不要求测试许可证。",
        )

    path = tester_license_path()
    if not path.is_file():
        return TesterLicenseStatus(
            required=True,
            state=TesterLicenseState.MISSING,
            active=False,
            release_label=TESTER_RELEASE_LABEL,
            detail="首次使用需要输入测试许可证。",
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
            release_label=TESTER_RELEASE_LABEL,
            detail="已保存的测试许可证无法读取。",
        )


def activate_tester_license(token: str, *, now: datetime | None = None) -> TesterLicenseStatus:
    status = verify_tester_license_token(token, now=now)
    directory = tester_license_dir()
    directory.mkdir(parents=True, exist_ok=True)
    if directory.is_symlink():
        raise TesterLicenseError(TesterLicenseState.INVALID, "测试许可证目录不能是符号链接。")
    path = tester_license_path()
    if path.is_symlink():
        raise TesterLicenseError(TesterLicenseState.INVALID, "测试许可证文件不能是符号链接。")
    atomic_write_text(path, token.strip() + "\n")
    return status


def active_tester_watermark() -> str | None:
    if not tester_license_required():
        return None
    status = current_tester_license_status()
    if not status.active or not status.tester_id:
        return None
    return f"Law-Rag {TESTER_RELEASE_LABEL} · Tester {status.tester_id} · Limited Test Build"


class TesterLicenseMiddleware:
    """Fail closed on release API calls until the signed tester license is active.

    Static SPA files stay reachable so the first-launch activation screen can be
    rendered. Only the two license endpoints and health are reachable before
    activation; every other /api request is locked at the ASGI boundary.
    """

    _ALLOWED_API_PATHS = {
        "/api/health",
        "/api/tester-license/status",
        "/api/tester-license/activate",
    }

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http" or not tester_license_required():
            await self.app(scope, receive, send)
            return
        path = str(scope.get("path") or "")
        if path.startswith("/api/") and path not in self._ALLOWED_API_PATHS:
            status = current_tester_license_status()
            if not status.active:
                response = JSONResponse(
                    status_code=423,
                    content={
                        "detail": "Law-Rag limited tester license is required before this API can be used.",
                        "tester_license": status.model_dump(mode="json"),
                    },
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
