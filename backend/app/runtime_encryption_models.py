from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

RUNTIME_ENCRYPTION_SCHEMA_VERSION = "1.0.0"


class RuntimeEncryptionMode(str, Enum):
    OFF = "OFF"
    AUTO = "AUTO"
    REQUIRED = "REQUIRED"


class RuntimeEncryptionState(str, Enum):
    DISABLED = "DISABLED"
    ENCRYPTED = "ENCRYPTED"
    DEGRADED = "DEGRADED"
    UNSUPPORTED = "UNSUPPORTED"


class RuntimeEncryptionOverview(BaseModel):
    schema_version: str = RUNTIME_ENCRYPTION_SCHEMA_VERSION
    mode: RuntimeEncryptionMode
    state: RuntimeEncryptionState
    platform: str
    backend: str = "WINDOWS_EFS"
    managed_root_names: list[str] = Field(default_factory=list)
    protected_root_names: list[str] = Field(default_factory=list)
    unprotected_root_names: list[str] = Field(default_factory=list)
    shared_legal_managed: bool = False
    detail: str
    warnings: list[str] = Field(default_factory=list)


class RuntimeEncryptionUpdateRequest(BaseModel):
    mode: RuntimeEncryptionMode
